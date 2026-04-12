import uuid
import os
import mercadopago
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for
from database import get_db

app = Flask(__name__)
app.secret_key = 'mamba_super_secret_session_key'

# MP Access Token (Coloque seu Access Token de Produção ou Teste aqui)
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "TEST-00000000000-000000-000000000000-000000000")
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

def log_acesso(email):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO acessos (id, email, data_hora) VALUES (%s, %s, %s)',
              (str(uuid.uuid4()), email, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    return dict(current_user=session.get('user_id'), user_role=session.get('role'), user_name=session.get('user_name'))

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('password')
        
        conn = get_db()
        user = conn.execute('SELECT * FROM usuarios WHERE email = %s AND senha = %s', (email, senha)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['nome']
            session['user_email'] = user['email']
            session['role'] = user['role']
            log_acesso(email)
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
            
        return render_template('login.html', error="Email ou senha incorretos", title="Login | Mamba Arena")
    return render_template('login.html', title="Login | Mamba Arena")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('password')
        
        conn = get_db()
        c = conn.cursor()
        
        user_exists = c.execute('SELECT id FROM usuarios WHERE email = %s', (email,)).fetchone()
        if user_exists:
            conn.close()
            return render_template('register.html', error="Email já cadastrado", title="Registro | Mamba Arena")
            
        novo_id = str(uuid.uuid4())
        role = "user"
        c.execute('INSERT INTO usuarios (id, nome, email, senha, role) VALUES (%s, %s, %s, %s, %s)',
                  (novo_id, nome, email, senha, role))
        conn.commit()
        conn.close()
        
        session['user_id'] = novo_id
        session['user_name'] = nome
        session['user_email'] = email
        session['role'] = role
        log_acesso(email)
        
        return redirect(url_for('index'))
    return render_template('register.html', title="Registro | Mamba")

# --- MAIN APP ROUTES ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', title="Início | Equipe Mamba")

@app.route('/placar')
@login_required
def placar():
    conn = get_db()
    jogos = conn.execute('SELECT * FROM jogos ORDER BY id ASC').fetchall()
    
    # We need to build competicoes with their rankings nested
    comps_rows = conn.execute('SELECT * FROM competicoes ORDER BY id ASC').fetchall()
    competicoes = []
    for c in comps_rows:
        comp_dict = dict(c)
        ranks = conn.execute('SELECT * FROM ranking WHERE competicao_id = %s ORDER BY posicao ASC', (c['id'],)).fetchall()
        comp_dict['ranking'] = [dict(r) for r in ranks]
        competicoes.append(comp_dict)
        
    conn.close()
    return render_template('placar.html', title="Placar | Equipe Mamba", jogos=jogos, competicoes=competicoes)

@app.route('/loja')
@login_required
def loja():
    conn = get_db()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()
    return render_template('loja.html', title="Loja | Equipe Mamba", produtos=produtos)

@app.route('/checkout/<product_id>', methods=['GET'])
@login_required
def checkout(product_id):
    conn = get_db()
    product = conn.execute('SELECT * FROM produtos WHERE id = %s', (product_id,)).fetchone()
    conn.close()
    
    if not product:
        abort(404, description="Produto não encontrado")
    return render_template('checkout.html', title="Finalizar Compra", product=product)

@app.route('/api/checkout', methods=['POST'])
@login_required
def api_checkout():
    req = request.json
    novo_pedido = {
        "id": str(uuid.uuid4()),
        "usuario_id": session.get('user_id'),
        "nome_cliente": session.get('user_name'),
        "email_cliente": session.get('user_email'),
        "telefone": req.get('telefone'),
        "descricao": req.get('descricao'),
        "produto_id": req.get('product_id'),
        "produto_nome": req.get('product_name'),
        "total": req.get('amount'),
        "status": "Pendente",
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    conn = get_db()
    conn.execute('''INSERT INTO pedidos 
                    (id, usuario_id, nome_cliente, email_cliente, telefone, descricao, produto_id, produto_nome, total, status, data_hora)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                 (novo_pedido['id'], novo_pedido['usuario_id'], novo_pedido['nome_cliente'], novo_pedido['email_cliente'], 
                  novo_pedido['telefone'], novo_pedido['descricao'], novo_pedido['produto_id'], novo_pedido['produto_nome'], 
                  novo_pedido['total'], novo_pedido['status'], novo_pedido['data_hora']))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "pedido_id": novo_pedido["id"]})

@app.route('/api/pix/<product_id>')
@login_required
def api_pix(product_id):
    conn = get_db()
    product = conn.execute('SELECT * FROM produtos WHERE id = %s', (product_id,)).fetchone()
    conn.close()
    if not product:
        return jsonify({"error": "Produto não encontrado"}), 404
        
    payment_data = {
        "transaction_amount": float(product['preco']),
        "description": f"Compra na Mamba: {product['nome']}",
        "payment_method_id": "pix",
        "payer": {
            "email": session.get('user_email')
        }
    }
    
    try:
        # Create payment via MercadoPago SDK
        payment_response = mp_sdk.payment().create(payment_data)
        payment = payment_response["response"]
        
        if payment.get("status") == "pending":
            transaction_data = payment.get("point_of_interaction", {}).get("transaction_data", {})
            return jsonify({
                "payload": transaction_data.get("qr_code"),
                "amount": float(product['preco']),
                "qr_code_base64": transaction_data.get("qr_code_base64")
            })
        else:
            return jsonify({"error": f"Erro MP: {payment.get('message', 'Desconhecido')}"}), 400
            
    except Exception as e:
        # Fallback fake se tiver erro no token
        return jsonify({"error": f"Erro com o Mercado Pago. Tem certeza que o Access Token é válido%s Detalhes: {str(e)}"}), 500

# --- ADMIN ROUTES ---
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    pedidos = conn.execute('SELECT * FROM pedidos ORDER BY data_hora DESC').fetchall()
    acessos = conn.execute('SELECT * FROM acessos ORDER BY data_hora DESC').fetchall()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    jogos = conn.execute('SELECT * FROM jogos ORDER BY id ASC').fetchall()
    
    comps_rows = conn.execute('SELECT * FROM competicoes ORDER BY id ASC').fetchall()
    competicoes = []
    for c in comps_rows:
        comp_dict = dict(c)
        ranks = conn.execute('SELECT * FROM ranking WHERE competicao_id = %s ORDER BY posicao ASC', (c['id'],)).fetchall()
        comp_dict['ranking'] = [dict(r) for r in ranks]
        competicoes.append(comp_dict)
    
    lucro_bruto = 0.0
    lucro_liquido = 0.0
    custos = {p['id']: float(p['custo']) for p in produtos}
    
    for p in pedidos:
        if p['status'] == 'Entregue':
            total = float(p['total'])
            custo_item = custos.get(p['produto_id'], 0.0)
            lucro_bruto += total
            lucro_liquido += (total - custo_item)
            
    # --- CHART DATA PREPARATION ---
    import collections
    from datetime import datetime as dt
    
    # 1. Vendas por Data (Lucro Diário)
    lucros_por_dia = collections.defaultdict(float)
    # 2. Vendas por Produto (Quantidade)
    vendas_produto = collections.defaultdict(int)
    
    for p in pedidos:
        if p['status'] == 'Entregue':
            try:
                # "data_hora": "11/04/2026 14:30" => Extract just "DD/MM"
                dia_str = p['data_hora'][:5]  
                custo_item = custos.get(p['produto_id'], 0.0)
                lucro_venda = float(p['total']) - custo_item
                lucros_por_dia[dia_str] += lucro_venda
            except:
                pass
            
            nome_prod = p['produto_nome']
            if not nome_prod: nome_prod = p['produto_id']
            vendas_produto[nome_prod] += 1
            
    # Sort them by date logic
    datas_ordenadas = sorted(lucros_por_dia.keys())
    chart_lucro_labels = datas_ordenadas[-15:] # Last 15 days max
    chart_lucro_dados = [round(lucros_por_dia[d], 2) for d in chart_lucro_labels]
    
    chart_pizza_labels = list(vendas_produto.keys())
    chart_pizza_dados = list(vendas_produto.values())
            
    conn.close()
    return render_template('admin.html', title="Painel Administrativo", 
                           pedidos=pedidos, acessos=acessos, produtos=produtos, 
                           jogos=jogos, competicoes=competicoes,
                           lucro_bruto=lucro_bruto, lucro_liquido=lucro_liquido,
                           chart_lucro_labels=chart_lucro_labels, chart_lucro_dados=chart_lucro_dados,
                           chart_pizza_labels=chart_pizza_labels, chart_pizza_dados=chart_pizza_dados)

@app.route('/api/admin/pedidos/<pedido_id>/status', methods=['POST'])
@admin_required
def update_pedido_status(pedido_id):
    novo_status = request.json.get('status')
    conn = get_db()
    conn.execute('UPDATE pedidos SET status = %s WHERE id = %s', (novo_status, pedido_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/pedidos/<pedido_id>', methods=['DELETE'])
@admin_required
def delete_pedido(pedido_id):
    conn = get_db()
    conn.execute('DELETE FROM pedidos WHERE id = %s', (pedido_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/produtos', methods=['PUT'])
@admin_required
def create_produto():
    prod_id = f"produto-{str(uuid.uuid4())[:8]}"
    conn = get_db()
    conn.execute('''INSERT INTO produtos (id, nome, preco, descricao, imagem, custo) 
                    VALUES (%s, %s, %s, %s, %s, %s)''', 
                 (prod_id, "Novo Produto", 0.0, "Descrição padrão", "camisa.png", 0.0))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/produtos/<produto_id>', methods=['POST'])
@admin_required
def update_produto(produto_id):
    req = request.json
    nome = req.get('nome')
    imagem = req.get('imagem')
    preco = req.get('preco')
    custo = req.get('custo')
    conn = get_db()
    conn.execute('UPDATE produtos SET nome = %s, imagem = %s, preco = %s, custo = %s WHERE id = %s', 
                 (nome, imagem, preco, custo, produto_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/produtos/<produto_id>', methods=['DELETE'])
@admin_required
def delete_produto(produto_id):
    conn = get_db()
    conn.execute('DELETE FROM produtos WHERE id = %s', (produto_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/jogos', methods=['PUT'])
@admin_required
def create_jogo():
    conn = get_db()
    conn.execute('''INSERT INTO jogos (time_a, time_b, pontos_a, pontos_b, status, data, especificacao) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)''', 
                 ("Time A", "Time B", 0, 0, "Agendado", "Em Breve", ""))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/jogos/<int:jogo_id>', methods=['POST'])
@admin_required
def update_jogo(jogo_id):
    req = request.json
    conn = get_db()
    conn.execute('UPDATE jogos SET pontos_a = %s, pontos_b = %s, status = %s, especificacao = %s WHERE id = %s',
                 (req.get('pontos_a'), req.get('pontos_b'), req.get('status'), req.get('especificacao'), jogo_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/jogos/<int:jogo_id>', methods=['DELETE'])
@admin_required
def delete_jogo(jogo_id):
    conn = get_db()
    conn.execute('DELETE FROM jogos WHERE id = %s', (jogo_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/competicoes', methods=['PUT'])
@admin_required
def create_competicao():
    comp_id = str(uuid.uuid4())
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO competicoes (id, nome, status) VALUES (%s, %s, %s)', (comp_id, "Nova Competição", "AGENDADO"))
    for pos, rank, equipe in [("1º", "🏆", "Mamba"), ("2º", "🥈", "Palawa"), ("3º", "🥉", "Salvatore")]:
        c.execute('INSERT INTO ranking (competicao_id, posicao, equipe, icone, destaque) VALUES (%s, %s, %s, %s, %s)',
                  (comp_id, pos, equipe, rank, equipe == "Mamba"))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/competicoes/<comp_id>', methods=['POST'])
@admin_required
def update_competicao(comp_id):
    req = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE competicoes SET nome = %s, status = %s WHERE id = %s',
              (req.get('nome'), req.get('status'), comp_id))
              
    ranking = req.get('ranking', [])
    c.execute('DELETE FROM ranking WHERE competicao_id = %s', (comp_id,))
    for r in ranking:
        c.execute('INSERT INTO ranking (competicao_id, posicao, equipe, icone, destaque) VALUES (%s, %s, %s, %s, %s)',
                  (comp_id, r.get('posicao'), r.get('equipe'), r.get('icone'), r.get('destaque')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/competicoes/<comp_id>', methods=['DELETE'])
@admin_required
def delete_competicao(comp_id):
    conn = get_db()
    conn.execute('DELETE FROM competicoes WHERE id = %s', (comp_id,))
    conn.execute('DELETE FROM ranking WHERE competicao_id = %s', (comp_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
