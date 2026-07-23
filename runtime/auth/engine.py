from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.safety.file_system_guard import safe_write_file

from .config import AuthProvider


@dataclass
class AuthIntegrationResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    providers_installed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class AuthIntegrationEngine:
    def __init__(self, target_dir: Path | str, provider: AuthProvider):
        self.target_dir = Path(target_dir)
        self.provider = provider
        self.result = AuthIntegrationResult()

    def run(self) -> AuthIntegrationResult:
        validation_errors = self.provider.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._validate_project()
        if self.result.errors:
            return self.result

        self._ensure_package_dep()
        self._write_auth_provider()
        self._write_sign_in_button()
        self._write_user_button()
        self._write_protected_route()
        self._write_sign_in_page()
        self._write_env_example()
        self._write_middleware()

        if self.provider.enabled:
            self.result.providers_installed.append(self.provider.provider_id)
        return self.result

    def _write_file(self, rel_path: str, content: str) -> None:
        try:
            safe_write_file(self.target_dir, rel_path, content)
            self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _validate_project(self) -> None:
        package = self.target_dir / "package.json"
        if not package.exists():
            self.result.errors.append({"file": "package.json", "reason": "missing package.json; target_dir is not a Next.js project"})

    def _ensure_package_dep(self) -> None:
        package_path = self.target_dir / "package.json"
        if not package_path.exists():
            return
        dep_map = {
            "clerk": "@clerk/nextjs",
            "auth0": "@auth0/nextjs-auth0",
        }
        dep_name = dep_map.get(self.provider.provider_id)
        if not dep_name:
            return
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
            deps = data.setdefault("dependencies", {})
            if dep_name not in deps:
                deps[dep_name] = "^5.0.0" if self.provider.provider_id == "clerk" else "^3.5.0"
                package_path.write_text(_stable_json(data), encoding="utf-8")
                self.result.files_modified.append("package.json")
        except Exception as exc:
            self.result.errors.append({"file": "package.json", "reason": str(exc)})

    def _write_auth_provider(self) -> None:
        if self.provider.provider_id == "clerk":
            code = """import { ClerkProvider } from "@clerk/nextjs";

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  return <ClerkProvider>{children}</ClerkProvider>;
}
"""
        else:
            code = """"use client";

import { UserProvider } from "@auth0/nextjs-auth0/client";

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  return <UserProvider>{children}</UserProvider>;
}
"""
        self._write_file("src/components/auth/AuthProvider.tsx", code)

    def _write_sign_in_button(self) -> None:
        if self.provider.provider_id == "clerk":
            code = """import { SignInButton as ClerkSignInButton } from "@clerk/nextjs";

export default function SignInButton() {
  return <ClerkSignInButton mode="modal" />;
}
"""
        else:
            code = """export default function SignInButton() {
  return (
    <a
      href="/api/auth/login"
      className="rounded bg-slate-900 px-3 py-2 text-sm text-white"
    >
      Sign in
    </a>
  );
}
"""
        self._write_file("src/components/auth/SignInButton.tsx", code)

    def _write_user_button(self) -> None:
        if self.provider.provider_id == "clerk":
            code = """import { UserButton as ClerkUserButton } from "@clerk/nextjs";

export default function UserButton() {
  return <ClerkUserButton />;
}
"""
        else:
            code = """"use client";

import { useUser } from "@auth0/nextjs-auth0/client";

export default function UserButton() {
  const { user, error, isLoading } = useUser();
  if (isLoading) return <span>Loading...</span>;
  if (error) return <span>Error</span>;
  if (!user) return <a href="/api/auth/login">Sign in</a>;
  return (
    <div className="flex items-center gap-2">
      <span>{user.name || user.email}</span>
      <a href="/api/auth/logout">Sign out</a>
    </div>
  );
}
"""
        self._write_file("src/components/auth/UserButton.tsx", code)

    def _write_protected_route(self) -> None:
        if self.provider.provider_id == "clerk":
            code = """import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

export default async function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session.userId) redirect("/sign-in");
  return <>{children}</>;
}
"""
        else:
            code = """import { getSession } from "@auth0/nextjs-auth0";
import { redirect } from "next/navigation";

export default async function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session?.user) redirect("/api/auth/login");
  return <>{children}</>;
}
"""
        self._write_file("src/components/auth/ProtectedRoute.tsx", code)

    def _write_sign_in_page(self) -> None:
        code = """import SignInButton from "@/components/auth/SignInButton";

export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <SignInButton />
    </main>
  );
}
"""
        self._write_file("src/app/sign-in/page.tsx", code)

    def _write_env_example(self) -> None:
        if self.provider.provider_id == "clerk":
            lines = [
                "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=",
                "CLERK_SECRET_KEY=",
                f"NEXT_PUBLIC_CLERK_SIGN_IN_URL={self.provider.redirect_uri or '/sign-in'}",
                "NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up",
                "NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/",
                "NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/",
            ]
        else:
            base_url = self.provider.redirect_uri or "http://localhost:3000"
            lines = [
                f"AUTH0_DOMAIN={self.provider.domain or ''}",
                f"AUTH0_CLIENT_ID={self.provider.client_id or ''}",
                "AUTH0_CLIENT_SECRET=",
                "AUTH0_SECRET=",
                f"AUTH0_BASE_URL={base_url}",
                f"APP_BASE_URL={base_url}",
            ]
        self._write_file(".env.local.example", "\n".join(lines) + "\n")

    def _write_middleware(self) -> None:
        middleware_path = self.target_dir / "middleware.ts"
        if middleware_path.exists():
            self.result.notes.append("middleware.ts already exists; auth middleware not written")
            return

        protected = self.provider.protected_paths or (
            ["/dashboard(.*)"] if self.provider.provider_id == "clerk" else ["/dashboard/:path*"]
        )
        matcher = json.dumps(protected)
        if self.provider.provider_id == "clerk":
            code = f"""import {{ clerkMiddleware, createRouteMatcher }} from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher({matcher});

export default clerkMiddleware((auth, req) => {{
  if (isProtectedRoute(req)) auth().protect();
}});

export const config = {{
  matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
}};
"""
        else:
            code = f"""import {{ withMiddlewareAuthRequired }} from "@auth0/nextjs-auth0/middleware";

export default withMiddlewareAuthRequired();

export const config = {{
  matcher: {matcher},
}};
"""
        self._write_file("middleware.ts", code)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
