/*
  Warnings:

  - Added the required column `dataSourceId` to the `Session` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "Session" ADD COLUMN     "dataSourceId" TEXT NOT NULL;

-- CreateIndex
CREATE INDEX "Session_dataSourceId_idx" ON "Session"("dataSourceId");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_dataSourceId_fkey" FOREIGN KEY ("dataSourceId") REFERENCES "DataSource"("id") ON DELETE CASCADE ON UPDATE CASCADE;
