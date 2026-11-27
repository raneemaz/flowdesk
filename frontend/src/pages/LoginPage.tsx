import { useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Logo } from "@/components/Logo";
import { Turnstile, TURNSTILE_SITE_KEY, type TurnstileHandle } from "@/components/Turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { loginSchema, type LoginFormValues } from "@/features/auth/schemas";

interface LocationState {
  from?: { pathname: string };
  justRegistered?: boolean;
}

export function LoginPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const [botToken, setBotToken] = useState<string | null>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const justRegistered = (location.state as LocationState | null)?.justRegistered ?? false;

  // Already logged in (e.g. navigated here directly with a live
  // session) - no reason to show the form again.
  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    if (TURNSTILE_SITE_KEY && !botToken) {
      setFormError("Please complete the security check first.");
      return;
    }
    try {
      await login(values.email, values.password, botToken ?? undefined);
      const redirectTo = (location.state as LocationState | null)?.from?.pathname ?? "/";
      navigate(redirectTo, { replace: true });
    } catch (error) {
      // The backend deliberately returns the identical 401 for an
      // unknown email and a wrong password (docs/API.md) - this just
      // surfaces that message as-is rather than guessing at something
      // more specific.
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      // Turnstile tokens are single-use: get a fresh one for the retry.
      turnstileRef.current?.reset();
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4 py-10 text-foreground">
      <Link to="/welcome" aria-label="FlowDesk home">
        <Logo size={36} />
      </Link>
      <div className="w-full max-w-sm rounded-md border border-border bg-card p-4 sm:p-6 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold">Log in to FlowDesk</h1>

        {justRegistered && (
          <p className="mb-4 rounded-md bg-success/10 px-3 py-2 text-sm text-success">
            Account created. Log in to continue.
          </p>
        )}

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={errors.email ? "true" : "false"}
              {...registerField("email")}
            />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={errors.password ? "true" : "false"}
              {...registerField("password")}
            />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>

          {formError && (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}

          {TURNSTILE_SITE_KEY && <Turnstile ref={turnstileRef} action="login" onToken={setBotToken} />}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Logging in…" : "Log in"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-foreground/70">
          Don&apos;t have an account?{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Register
          </Link>
        </p>
      </div>
    </main>
  );
}
