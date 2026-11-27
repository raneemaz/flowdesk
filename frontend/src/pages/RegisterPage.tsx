import { useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Logo } from "@/components/Logo";
import { Turnstile, TURNSTILE_SITE_KEY, type TurnstileHandle } from "@/components/Turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { registerSchema, type RegisterFormValues } from "@/features/auth/schemas";

export function RegisterPage() {
  const { register: registerAccount, status } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const [botToken, setBotToken] = useState<string | null>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({ resolver: zodResolver(registerSchema) });

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (values: RegisterFormValues) => {
    setFormError(null);
    if (TURNSTILE_SITE_KEY && !botToken) {
      setFormError("Please complete the security check first.");
      return;
    }
    try {
      await registerAccount(values.name, values.email, values.password, botToken ?? undefined);
      // Registration never starts a session (docs/API.md) - log in is
      // a separate, explicit step.
      navigate("/login", { replace: true, state: { justRegistered: true } });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      turnstileRef.current?.reset();
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4 py-10 text-foreground">
      <Link to="/welcome" aria-label="FlowDesk home">
        <Logo size={36} />
      </Link>
      <div className="w-full max-w-sm rounded-md border border-border bg-card p-4 sm:p-6 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold">Create your FlowDesk account</h1>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" autoComplete="name" aria-invalid={errors.name ? "true" : "false"} {...registerField("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

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
              autoComplete="new-password"
              aria-invalid={errors.password ? "true" : "false"}
              {...registerField("password")}
            />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirmPassword">Confirm password</Label>
            <Input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              aria-invalid={errors.confirmPassword ? "true" : "false"}
              {...registerField("confirmPassword")}
            />
            {errors.confirmPassword && <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>}
          </div>

          {formError && (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}

          {TURNSTILE_SITE_KEY && <Turnstile ref={turnstileRef} action="signup" onToken={setBotToken} />}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-foreground/70">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
