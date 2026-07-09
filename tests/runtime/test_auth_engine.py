"""Tests for runtime/auth engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.auth.config import AuthProvider
from runtime.auth.engine import AuthIntegrationEngine


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    return tmp_path


def test_clerk_writes_auth_files_and_dependency(tmp_path):
    root = _make_project(tmp_path)
    provider = AuthProvider(provider_id="clerk")
    engine = AuthIntegrationEngine(root, provider)
    result = engine.run()

    assert not result.errors
    assert "clerk" in result.providers_installed
    assert any("src/components/auth/AuthProvider.tsx" in f for f in result.files_written)
    assert any("src/components/auth/SignInButton.tsx" in f for f in result.files_written)
    assert any("src/components/auth/UserButton.tsx" in f for f in result.files_written)
    assert any("src/components/auth/ProtectedRoute.tsx" in f for f in result.files_written)
    assert any("src/app/sign-in/page.tsx" in f for f in result.files_written)
    assert any(".env.local.example" in f for f in result.files_written)
    assert any("middleware.ts" in f for f in result.files_written)
    assert any("package.json" in f for f in result.files_modified)

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["@clerk/nextjs"]

    env_example = (root / ".env.local.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" in env_example



def test_auth0_writes_auth_files_and_dependency(tmp_path):
    root = _make_project(tmp_path)
    provider = AuthProvider(
        provider_id="auth0",
        domain="example.auth0.com",
        client_id="client-id",
        redirect_uri="https://demo.example.com",
    )
    engine = AuthIntegrationEngine(root, provider)
    result = engine.run()

    assert not result.errors
    assert "auth0" in result.providers_installed
    assert any("src/components/auth/AuthProvider.tsx" in f for f in result.files_written)
    assert any("src/components/auth/SignInButton.tsx" in f for f in result.files_written)
    assert any("src/components/auth/UserButton.tsx" in f for f in result.files_written)
    assert any("src/components/auth/ProtectedRoute.tsx" in f for f in result.files_written)
    assert any("src/app/sign-in/page.tsx" in f for f in result.files_written)
    assert any(".env.local.example" in f for f in result.files_written)
    assert any("middleware.ts" in f for f in result.files_written)
    assert any("package.json" in f for f in result.files_modified)

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["@auth0/nextjs-auth0"]

    env_example = (root / ".env.local.example").read_text(encoding="utf-8")
    assert "AUTH0_DOMAIN" in env_example
    assert "example.auth0.com" in env_example



def test_existing_middleware_not_overwritten(tmp_path):
    root = _make_project(tmp_path)
    existing = "export const config = { matcher: ['/'] };\n"
    (root / "middleware.ts").write_text(existing, encoding="utf-8")

    provider = AuthProvider(provider_id="clerk")
    engine = AuthIntegrationEngine(root, provider)
    result = engine.run()

    assert not result.errors
    assert not any("middleware.ts" in f for f in result.files_written)
    assert any("middleware.ts already exists" in n for n in result.notes)
    assert (root / "middleware.ts").read_text(encoding="utf-8") == existing



def test_disabled_provider_skips_install(tmp_path):
    root = _make_project(tmp_path)
    provider = AuthProvider(provider_id="clerk", enabled=False)
    engine = AuthIntegrationEngine(root, provider)
    result = engine.run()

    assert not result.errors
    assert result.providers_installed == []
