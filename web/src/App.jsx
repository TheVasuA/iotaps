import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import router from "./router";

// App root: provides the router and the global Sonner toaster (used for
// command ACK feedback, notifications, and theme-toggle failure messages).
export default function App() {
  return (
    <>
      <RouterProvider router={router} />
      <Toaster position="bottom-left" richColors closeButton toastOptions={{ className: "text-xs" }} />
    </>
  );
}
