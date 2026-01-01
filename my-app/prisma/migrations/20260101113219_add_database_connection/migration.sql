-- DropIndex
DROP INDEX "DataSource_userId_cloudinaryUrl_key";

-- AlterTable
ALTER TABLE "DataSource" ADD COLUMN     "connectionType" TEXT NOT NULL DEFAULT 'FILE',
ADD COLUMN     "dbHost" TEXT,
ADD COLUMN     "dbName" TEXT,
ADD COLUMN     "dbPassword" TEXT,
ADD COLUMN     "dbPort" INTEGER,
ADD COLUMN     "dbType" TEXT,
ADD COLUMN     "dbUsername" TEXT,
ADD COLUMN     "displayName" TEXT,
ALTER COLUMN "cloudinaryUrl" DROP NOT NULL;

-- CreateIndex
CREATE INDEX "DataSource_connectionType_idx" ON "DataSource"("connectionType");
