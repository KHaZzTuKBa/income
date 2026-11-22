import { type FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router-dom";
import { getMe, homePath, register } from "../api/auth";
import {
  AuthShell,
  Spinner,
  authButtonClass,
  authInputClass,
  authInputErrorClass,
} from "../components/AuthShell";
import { LoadingScreen } from "../components/LoadingScreen";
import { type RegisterErrors, type RegisterForm, normalizePhone, validateRegistration } from "../validation";

const EMPTY: RegisterForm = { username: "", email: "", phone: "", password: "", confirm: "" };

type FieldProps = {
  label: string;
  name: keyof RegisterForm;
  form: RegisterForm;
  errors: RegisterErrors;
  onChange: (name: keyof RegisterForm, value: string) => void;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
  inputMode?: "text" | "email" | "tel";
};

function Field({ label, name, form, errors, onChange, type = "text", autoComplete, placeholder, inputMode }: FieldProps) {
  const error = errors[name];
  return (
    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
      {label}
      <input
        type={type}
        name={name}
        className={error ? authInputErrorClass : authInputClass}
        value={form[name]}
        onChange={(event) => onChange(name, event.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        inputMode={inputMode}
        aria-invalid={error ? true : undefined}
      />
      {error ? <span className="mt-1 block text-xs font-medium normal-case tracking-normal text-red-600">{error}</span> : null}
    </label>
  );
}

export function RegisterPage() {
  const [form, setForm] = useState<RegisterForm>(EMPTY);
  const [submitted, setSubmitted] = useState(false);

  const { data: user, isLoading } = useQuery({ queryKey: ["me"], queryFn: getMe });

  const mutation = useMutation({
    mutationFn: () =>
      register({
        username: form.username.trim(),
        email: form.email.trim(),
        phone: normalizePhone(form.phone) ?? form.phone,
        password: form.password,
      }),
  });

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (user) {
    return <Navigate to={homePath(user)} replace />;
  }

  if (mutation.isSuccess) {
    return (
      <AuthShell subtitle="Регистрация">
        <div className="mt-8 space-y-5 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
            <svg viewBox="0 0 16 16" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M3 8.5l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <p className="text-lg font-bold text-slate-900">Данные отправлены на проверку</p>
            <p className="mt-2 text-sm text-slate-600">
              Администратор рассмотрит заявку. После одобрения войдите с логином{" "}
              <span className="font-semibold text-slate-900">{form.username.trim().toLowerCase()}</span> и вашим
              паролем.
            </p>
          </div>
          <Link to="/login" className={authButtonClass}>
            Ко входу
          </Link>
        </div>
      </AuthShell>
    );
  }

  const errors: RegisterErrors = submitted ? validateRegistration(form) : {};

  function onChange(name: keyof RegisterForm, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(validateRegistration(form)).length > 0) {
      return;
    }
    mutation.mutate();
  }

  return (
    <AuthShell subtitle="Заявка на регистрацию">
      <form className="mt-8 space-y-4" onSubmit={onSubmit} noValidate>
        <Field label="Логин" name="username" form={form} errors={errors} onChange={onChange} autoComplete="username" placeholder="ivan.petrov" />
        <Field
          label="Почта"
          name="email"
          type="email"
          inputMode="email"
          form={form}
          errors={errors}
          onChange={onChange}
          autoComplete="email"
          placeholder="ivan@example.com"
        />
        <Field
          label="Телефон"
          name="phone"
          type="tel"
          inputMode="tel"
          form={form}
          errors={errors}
          onChange={onChange}
          autoComplete="tel"
          placeholder="+7 999 123-45-67"
        />
        <Field
          label="Пароль"
          name="password"
          type="password"
          form={form}
          errors={errors}
          onChange={onChange}
          autoComplete="new-password"
          placeholder="Минимум 8 символов, буквы и цифры"
        />
        <Field
          label="Повторите пароль"
          name="confirm"
          type="password"
          form={form}
          errors={errors}
          onChange={onChange}
          autoComplete="new-password"
        />
        {mutation.isError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/80 p-3 text-xs font-medium text-red-700">
            {mutation.error instanceof Error ? mutation.error.message : "Не удалось отправить заявку"}
          </div>
        ) : null}
        <button type="submit" disabled={mutation.isPending} className={authButtonClass}>
          {mutation.isPending ? (
            <>
              <Spinner />
              <span>Отправляем…</span>
            </>
          ) : (
            "Отправить заявку"
          )}
        </button>
        <p className="text-center text-sm text-slate-500">
          Уже есть аккаунт?{" "}
          <Link to="/login" className="font-semibold text-emerald-700 hover:text-emerald-800">
            Войти
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
