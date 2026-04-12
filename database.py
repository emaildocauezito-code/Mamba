import psycopg2
from psycopg2.extras import DictCursor

DB_URI = "postgresql://neondb_owner:npg_eop8uR5ibrqF@ep-young-lake-an74ljvg-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require"

class DBCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        res = self.cursor.fetchone()
        return dict(res) if res else None

    def fetchall(self):
        res = self.cursor.fetchall()
        return [dict(r) for r in res]

class DBWrapper:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URI)
        self.conn.autocommit = True

    def execute(self, query, params=()):
        cur = self.conn.cursor(cursor_factory=DictCursor)
        cur.execute(query, params)
        return DBCursorWrapper(cur)

    def commit(self):
        pass

    def close(self):
        self.conn.close()

def get_db():
    return DBWrapper()

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nome TEXT,
            email TEXT UNIQUE,
            senha TEXT,
            role TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jogos (
            id SERIAL PRIMARY KEY,
            time_a TEXT,
            time_b TEXT,
            pontos_a INTEGER,
            pontos_b INTEGER,
            status TEXT,
            data TEXT,
            especificacao TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS competicoes (
            id TEXT PRIMARY KEY,
            nome TEXT,
            status TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ranking (
            id SERIAL PRIMARY KEY,
            competicao_id TEXT,
            posicao TEXT,
            equipe TEXT,
            icone TEXT,
            destaque BOOLEAN,
            FOREIGN KEY(competicao_id) REFERENCES competicoes(id) ON DELETE CASCADE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id TEXT PRIMARY KEY,
            nome TEXT,
            preco REAL,
            descricao TEXT,
            imagem TEXT,
            custo REAL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id TEXT PRIMARY KEY,
            usuario_id TEXT,
            nome_cliente TEXT,
            email_cliente TEXT,
            telefone TEXT,
            descricao TEXT,
            produto_id TEXT,
            produto_nome TEXT,
            total REAL,
            status TEXT,
            data_hora TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS acessos (
            id TEXT PRIMARY KEY,
            email TEXT,
            data_hora TEXT
        )
    ''')
    conn.close()

if __name__ == '__main__':
    init_db()
    print("PostgreSQL Database tables initialized in Neon Cloud.")
