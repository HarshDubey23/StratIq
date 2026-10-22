import { ProjectProvider } from "@/components/ProjectContext";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ProjectProvider>{children}</ProjectProvider>;
}
