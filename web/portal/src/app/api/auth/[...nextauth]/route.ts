import NextAuth from "next-auth/next"
import { config } from "@/auth"
import { NextApiRequest, NextApiResponse } from "next";

const handler = NextAuth(config)
export {handler as GET, handler as POST}
// const wrapWithLogic = (handlerFunc: any) => async (req: NextApiRequest, res: NextApiResponse) => {
// 	// console.debug('Request:', req);
// 	// console.debug('Response:', res);
// 	// debugger;

// 	// Now call the actual handler
// 	return handlerFunc(req, res);
//   };

// export const GET = wrapWithLogic(handler);
// export const POST = wrapWithLogic(handler);
