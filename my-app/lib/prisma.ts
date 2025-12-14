import { PrismaClient } from "../generated/prisma";
import { PrismaPg } from "@prisma/adapter-pg";

const adapter = new PrismaPg({
  connectionString: process.env.DATABASE_URL!,
});

const prisma = new PrismaClient({ adapter });

// For Next.js hot reload safety:
const globalForPrisma = global as unknown as { prisma?: typeof prisma };

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma ??= prisma;
}

export default globalForPrisma.prisma ?? prisma;
