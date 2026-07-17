import { getServerSession } from "next-auth";
import { authOptions } from "./api/auth/[...nextauth]/route";
import Link from "next/link";

export default async function Home() {
  const session = await getServerSession(authOptions);

  return (
    <main className="p-8 max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-4">TypeScript Next.js Starter</h1>
      {session ? (
        <p>Welcome, {session.user?.email}!</p>
      ) : (
        <p>
          Please <Link href="/login" className="text-blue-600">login</Link>.
        </p>
      )}
    </main>
  );
}
