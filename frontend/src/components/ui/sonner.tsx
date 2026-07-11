import React from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

function Toaster(props: ToasterProps) {
  const [theme, setTheme] = React.useState<"light" | "dark">(() => document.documentElement.dataset.theme === "dark" ? "dark" : "light");

  React.useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => setTheme(root.dataset.theme === "dark" ? "dark" : "light"));
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return <Sonner theme={theme} className="toaster group" richColors closeButton {...props} />;
}

export { Toaster };
