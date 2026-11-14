import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
  type ButtonHTMLAttributes,
} from "react";
import { AlertCircle, LoaderCircle, SearchX, X } from "lucide-react";

export function Button({
  children,
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "text";
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function StatePanel({
  kind,
  title,
  children,
  retry,
}: {
  kind: "loading" | "error" | "empty" | "denied";
  title: string;
  children?: ReactNode;
  retry?: () => void;
}) {
  const Icon =
    kind === "loading"
      ? LoaderCircle
      : kind === "empty"
        ? SearchX
        : AlertCircle;
  return (
    <div className="state-panel" role={kind === "error" ? "alert" : "status"}>
      <Icon
        size={26}
        className={kind === "loading" ? "animate-spin" : ""}
        aria-hidden="true"
      />
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {retry && <Button onClick={retry}>Réessayer</Button>}
    </div>
  );
}

export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    return () => {
      dialog.close();
      const target =
        previous?.isConnected && !previous.matches(":disabled")
          ? previous
          : document.getElementById("main");
      target?.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className="dialog"
    >
      <div className="dialog-heading">
        <h2 id={id}>{title}</h2>
        <button
          type="button"
          className="icon-button"
          aria-label="Fermer"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "blue" | "green" | "amber" | "red";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
