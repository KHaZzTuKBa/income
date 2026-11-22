export type RegisterForm = {
  username: string;
  email: string;
  phone: string;
  password: string;
  confirm: string;
};

export type RegisterErrors = Partial<Record<keyof RegisterForm, string>>;

const USERNAME_RE = /^[a-zA-Z][a-zA-Z0-9_.-]*$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function normalizePhone(value: string): string | null {
  let digits = value.replace(/\D/g, "");
  if (digits.length === 11 && (digits[0] === "7" || digits[0] === "8")) {
    digits = digits.slice(1);
  } else if (!(digits.length === 10 && digits[0] === "9")) {
    return null;
  }
  return `+7${digits}`;
}

export function formatPhone(phone: string | null): string {
  if (!phone) {
    return "—";
  }
  const match = /^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/.exec(phone);
  return match ? `+7 ${match[1]} ${match[2]}-${match[3]}-${match[4]}` : phone;
}

export function validateUsername(value: string): string | null {
  const username = value.trim();
  if (username.length < 3 || username.length > 32) {
    return "От 3 до 32 символов";
  }
  if (!USERNAME_RE.test(username)) {
    return "Латинские буквы, цифры, точка, дефис и подчёркивание; начинается с буквы";
  }
  return null;
}

export function validatePassword(password: string, username: string): string | null {
  if (password.length < 8 || password.length > 128) {
    return "От 8 до 128 символов";
  }
  if (!/\p{L}/u.test(password) || !/\d/.test(password)) {
    return "Нужна хотя бы одна буква и одна цифра";
  }
  if (username.trim() && password.toLowerCase() === username.trim().toLowerCase()) {
    return "Не должен совпадать с логином";
  }
  return null;
}

export function validateRegistration(form: RegisterForm): RegisterErrors {
  const errors: RegisterErrors = {};
  const username = validateUsername(form.username);
  if (username) {
    errors.username = username;
  }
  const email = form.email.trim();
  if (!email || email.length > 254 || !EMAIL_RE.test(email)) {
    errors.email = "Некорректная почта";
  }
  if (!normalizePhone(form.phone)) {
    errors.phone = "Формат: +7 999 123-45-67";
  }
  const password = validatePassword(form.password, form.username);
  if (password) {
    errors.password = password;
  }
  if (form.confirm !== form.password) {
    errors.confirm = "Пароли не совпадают";
  }
  return errors;
}

export function plural(count: number, forms: [string, string, string]): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return forms[0];
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return forms[1];
  }
  return forms[2];
}
