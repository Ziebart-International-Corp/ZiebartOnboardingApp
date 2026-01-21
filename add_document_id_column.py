"""
Add document_id column to user_tasks table
"""
import pyodbc
from config import SQLALCHEMY_DATABASE_URI
from urllib.parse import urlparse, unquote

def add_document_id_column():
    """Add document_id column to user_tasks table"""
    # Parse connection string
    # Format: mssql+pyodbc://Developer:1Shot@OneKill@roadrunner:42278/NewHireApp?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
    
    # Remove the mssql+pyodbc:// prefix and get the base URL
    base_url = SQLALCHEMY_DATABASE_URI.replace('mssql+pyodbc://', 'http://')
    parsed = urlparse(base_url)
    
    # Extract username and password (they're in the netloc before @)
    # Format: Developer:1Shot@OneKill@roadrunner:42278
    netloc = parsed.netloc
    if '@' in netloc:
        # Split on last @ to separate credentials from server
        parts = netloc.rsplit('@', 1)
        credentials = parts[0]  # Developer:1Shot@OneKill
        server_part = parts[1]   # roadrunner:42278
        
        # Split credentials on first :
        if ':' in credentials:
            username = credentials.split(':', 1)[0]  # Developer
            password = credentials.split(':', 1)[1]  # 1Shot@OneKill
            password = unquote(password)  # Decode URL encoding if any
        else:
            username = credentials
            password = ''
    else:
        username = ''
        password = ''
        server_part = netloc
    
    # Extract server and port
    if ':' in server_part:
        server, port = server_part.split(':')
    else:
        server = server_part
        port = '1433'
    
    # Extract database from path
    database = parsed.path.lstrip('/').split('?')[0]  # NewHireApp
    
    # Build connection string for pyodbc
    odbc_conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},{port};DATABASE={database};UID={username};PWD={password};TrustServerCertificate=yes;"
    
    try:
        conn = pyodbc.connect(odbc_conn_str)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'user_tasks' 
            AND COLUMN_NAME = 'document_id'
        """)
        
        if cursor.fetchone()[0] == 0:
            print("Adding document_id column to user_tasks table...")
            cursor.execute("""
                ALTER TABLE user_tasks
                ADD document_id INT NULL
            """)
            conn.commit()
            print("Column added successfully!")
        else:
            print("Column document_id already exists.")
        
        # Add foreign key constraint if it doesn't exist
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS 
            WHERE TABLE_NAME = 'user_tasks' 
            AND CONSTRAINT_NAME = 'FK_user_tasks_document_id'
        """)
        
        if cursor.fetchone()[0] == 0:
            print("Adding foreign key constraint...")
            cursor.execute("""
                ALTER TABLE user_tasks
                ADD CONSTRAINT FK_user_tasks_document_id
                FOREIGN KEY (document_id) REFERENCES documents(id)
            """)
            conn.commit()
            print("Foreign key constraint added successfully!")
        else:
            print("Foreign key constraint already exists.")
        
        conn.close()
        print("\nDatabase update complete!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise

if __name__ == '__main__':
    add_document_id_column()
