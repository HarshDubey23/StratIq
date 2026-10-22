import { Suspense } from "react";
import { Wizard } from "./Wizard";

export default function Page() {
  return (
    <Suspense>
      <Wizard />
    </Suspense>
  );
}
