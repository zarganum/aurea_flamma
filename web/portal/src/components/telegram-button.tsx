// "use client";

import { LoginButton } from "@telegram-auth/react";

import { useSession, signIn, signOut } from "next-auth/react";

export function TelegramSignInButton({ botUsername }: { botUsername: string }) {
	const { data: session, status } = useSession();

	if (status === "loading") {
		return <>Loading...</>;
	}

	if (status === "authenticated") {
		return (
			<div>
				Logged as {session.user?.name}
				<button type="button" onClick={() => signOut()}>
					{" "}
					Sign out
				</button>
			</div>
		);
	}

	console.debug(TelegramSignInButton.name, status);
	return (
		<LoginButton
			botUsername={botUsername}
			widgetVersion={22}
			onAuthCallback={(data) => {
				signIn("telegram-login", { callbackUrl: "/" }, data as any);
			}}
		/>
	);
}
