import type { NextAuthOptions as NextAuthConfig } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { objectToAuthDataMap, AuthDataValidator } from "@telegram-auth/server";

import { ObjectId } from "mongodb";
import clientPromise from "@/app/api/auth/[...nextauth]/db";
import { JWT } from "next-auth/jwt/types";

declare module "next-auth" {
	interface Session {
		token?: JWT;
	}
}

declare module "next-auth/jwt" {
	interface JWT {
		/** The user's role. */
		userRole?: "admin";
	}
}

// Environment variable validation
declare global {
	namespace NodeJS {
		export interface ProcessEnv {
			NEXTAUTH_SECRET: string;
			TELEGRAM_BOT_TOKEN: string;
			NEXT_PUBLIC_TELEGRAM_BOT_USERNAME: string;
			MONGODB_URL: string;
		}
	}
}

export const config = {
	theme: {
		logo: "https://next-auth.js.org/img/logo/logo-sm.png",
	},
	providers: [
		CredentialsProvider({
			id: "telegram-login",
			name: "Telegram Login",
			credentials: {},
			async authorize(credentials, req) {
				const validator = new AuthDataValidator({
					botToken: `${process.env.TELEGRAM_BOT_TOKEN}`,
				});

				const data = objectToAuthDataMap(req.query || {});
				const user = await validator.validate(data);

				if (user.id && user.first_name) {
					const returned = {
						id: user.id.toString(),
						email: user.id.toString(),
						name: [user.first_name, user.last_name || ""].join(" "),
						image: user.photo_url,
					};

					// try {
					// 	await createUserOrUpdate(user);
					// } catch {
					// 	console.log(
					// 		"Something went wrong while creating the user."
					// 	);
					// }
					console.debug("authorize", returned);
					return returned;
				}
				return null;
			},
		}),
	],
	session: { strategy: "jwt" },
	callbacks: {
		async jwt({ token, user, account, profile }) {
			try {
				const user_id = parseInt(token.sub || "0", 10);
				const client = await clientPromise;
				const db = client.db();
				const dbUser = await db
					.collection("users")
					.findOne({ namespace: "tg", id: user_id });
				console.debug("callbacks.jwt dbUser", dbUser);
				if (dbUser) {
					token.claims = dbUser.portal_claims;
				}
			} catch (error) {
				console.error("callbacks.jwt error", error);
			}
			console.debug("callbacks.jwt token", token);
			return token;
		},
		async session({ session, user, token }) {
			// Attach the JWT to the session
			session.token = token;
			console.debug("callbacks.session", session);
			return session;
		},
	},
	debug: true,
} satisfies NextAuthConfig;

// // Helper function to get session without passing config every time
// // https://next-auth.js.org/configuration/nextjs#getserversession
// export function auth(...args: [GetServerSidePropsContext["req"], GetServerSidePropsContext["res"]] | [NextApiRequest, NextApiResponse] | []) {
// 	return getServerSession(...args, config)
//   }
