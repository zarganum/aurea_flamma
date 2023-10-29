import { MongoClient } from "mongodb";

declare global {
	var _mongoClientPromise: Promise<MongoClient> | undefined;
}

let client;
let clientPromise: Promise<MongoClient>;

const options = {
	useUnifiedTopology: true,
	useNewUrlParser: true,
};

if (!process.env.MONGODB_URL) {
	throw new Error("Please add your Mongo URI to .env.local");
}

if (process.env.NODE_ENV === "development") {
	// In development mode, use a global variable so the database is not repeatedly
	// connected and disconnected during hot module reloading.
	if (!global._mongoClientPromise) {
		client = new MongoClient(process.env.MONGODB_URL);
		global._mongoClientPromise = client.connect();
	}
	clientPromise = global._mongoClientPromise;
} else {
	// In production mode, it's best to not use a global variable.
	client = new MongoClient(process.env.MONGODB_URL);
	clientPromise = client.connect();
}

export default clientPromise;
