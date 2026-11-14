import { useState } from "react";
import { Button, Dialog } from "./ui";

export type Field = {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
  maxLength?: number;
  options?: { value: string; label: string }[];
};
export function DataEditor({
  title,
  description,
  fields,
  initial = {},
  save,
  close,
}: {
  title: string;
  description?: string;
  fields: Field[];
  initial?: Record<string, string>;
  save: (values: Record<string, string>) => Promise<void>;
  close: () => void;
}) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  return (
    <Dialog title={title} onClose={close}>
      <p className="muted mb-5">
        {description ??
          "Données commerciales AICED. Les attributs source restent en lecture seule."}
      </p>
      <form
        className="editor-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const data = Object.fromEntries(
            new FormData(event.currentTarget),
          ) as Record<string, string>;
          setError("");
          setPending(true);
          try {
            await save(data);
            close();
          } catch (failure) {
            setError(
              failure instanceof Error
                ? failure.message
                : "Enregistrement impossible.",
            );
          } finally {
            setPending(false);
          }
        }}
      >
        {fields.map((field) => (
          <label key={field.name}>
            {field.label}
            {field.options ? (
              <select
                aria-label={field.label}
                name={field.name}
                defaultValue={initial[field.name] ?? field.options[0]?.value}
                required={field.required}
              >
                {field.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : field.type === "textarea" ? (
              <textarea
                aria-label={field.label}
                name={field.name}
                defaultValue={initial[field.name] ?? ""}
                maxLength={field.maxLength ?? 5000}
                rows={4}
              />
            ) : (
              <input
                aria-label={field.label}
                name={field.name}
                type={field.type ?? "text"}
                defaultValue={initial[field.name] ?? ""}
                required={field.required}
                maxLength={field.maxLength ?? 160}
                min={field.type === "number" ? "0" : undefined}
                step={field.type === "number" ? ".001" : undefined}
              />
            )}
          </label>
        ))}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="editor-actions">
          <Button type="button" onClick={close} disabled={pending}>
            Annuler
          </Button>
          <Button variant="primary" type="submit" disabled={pending}>
            {pending ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
