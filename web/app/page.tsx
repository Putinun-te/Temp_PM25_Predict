import AboutNote from "@/components/AboutNote";
import Dashboard from "@/components/Dashboard";

// The page shell is exported as static HTML. Data is fetched in the browser,
// so the site shows each morning's forecast without being rebuilt.
export default function Page() {
  return (
    <main>
      <Dashboard />
      <AboutNote />
    </main>
  );
}
