import mongoose from "mongoose";

export interface User {
	_id: String;
	count: { identifications: Number };
	created_at: Date;
	updated_at: Date;
}

export async function connect() {
	const opts = {
		useNewUrlParser: true,
		useUnifiedTopology: true,
		bufferCommands: false,
	};

	return mongoose.connect(process.env.MONGODB_URL, opts).then((mongoose) => {
		return mongoose;
	}) as Promise<mongoose.Mongoose>;
}
