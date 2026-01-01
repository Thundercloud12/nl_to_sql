# Testing Database Connection Feature

## Setup Complete ✅

All code has been updated to support PostgreSQL database connections:

### Backend Changes:
1. ✅ **main.py** - `/query` endpoint detects `connectionType` and passes `db_config` to workflow
2. ✅ **plan_generator.py** - Added converter functions and updated State class
3. ✅ **interpretor.py** - Already handles PostgreSQL execution
4. ✅ **database_utilities.py** - PostgreSQLConnectionManager ready

### Database Schema:
- ✅ Migration applied: `20260101113219_add_database_connection`
- ✅ DataSource table now has: `connectionType`, `dbHost`, `dbPort`, `dbName`, `dbUsername`, `dbPassword`, `displayName`

### Frontend:
- ✅ Connection form at `/connect-database`
- ✅ Dashboard shows different icons for FILE vs DATABASE
- ✅ Navbar has "Connect Database" button

## How to Test:

### 1. Start Backend
```bash
cd backend
uvicorn main:app --reload
```

### 2. Start Frontend
```bash
cd my-app
npm run dev
```

### 3. Test Flow:

**A. Connect a Database:**
1. Navigate to http://localhost:3000/connect-database
2. Enter your PostgreSQL credentials:
   - Host: your-postgres-host.com
   - Port: 5432
   - Database: your_database
   - Username: your_username
   - Password: your_password
   - Display Name: "My Production DB"
3. Click "Test Connection" - should show success
4. Click "Connect Database" - saves to DataSource table

**B. View in Dashboard:**
1. Go to http://localhost:3000/dashboard
2. Your database should appear with a Database icon (vs FileSpreadsheet for files)
3. Display name should be "My Production DB"

**C. Query the Database:**
1. Click "Start Chat" on your database datasource
2. Ask a question: "Show me the first 10 rows from users table"
3. Backend will:
   - Detect connectionType = "DATABASE"
   - Fetch credentials from DataSource
   - Connect to your PostgreSQL database
   - Extract schema
   - Generate PostgreSQL SQL
   - Execute on your database
   - Return results

## Expected Behavior:

### For FILE datasources:
- Uses DuckDB
- Loads Parquet files
- Queries local data

### For DATABASE datasources:
- Uses psycopg2
- Connects to live PostgreSQL
- Queries remote data
- No file uploads needed

## Troubleshooting:

### If connection fails:
- Check PostgreSQL credentials
- Verify network access (firewall, security groups)
- Ensure PostgreSQL allows remote connections
- Check DATABASE_URL for app database is set

### If schema extraction fails:
- User needs SELECT permission on information_schema
- Database must be PostgreSQL (not MySQL/SQLite)

### If queries fail:
- Check SQL syntax is PostgreSQL-compatible
- Verify user has SELECT permission on tables
- Check if tables exist in the database

## Example Test Database:

If you don't have a PostgreSQL database, you can use a free tier from:
- **Neon** - https://neon.tech (serverless Postgres)
- **Supabase** - https://supabase.com (with GUI)
- **ElephantSQL** - https://www.elephantsql.com (managed)

Create a simple test table:
```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    price DECIMAL(10,2),
    category VARCHAR(50)
);

INSERT INTO products (name, price, category) VALUES
('Laptop', 999.99, 'Electronics'),
('Mouse', 29.99, 'Electronics'),
('Desk', 299.99, 'Furniture'),
('Chair', 199.99, 'Furniture');
```

Then ask: "What's the average price by category?"

## Next Steps:

After successful testing:
1. Add error handling for connection timeouts
2. Implement connection pooling for better performance
3. Add support for MySQL/SQLite (if needed)
4. Cache database schemas to reduce network calls
5. Add connection health checks

---

**Status:** Ready for end-to-end testing! 🚀
