import os
from io import BytesIO
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Espaço Máximos | Estoque & Vendas", page_icon="🌸", layout="wide")

PINK = "#D94D8C"
ROSE = "#A92F66"
DARK = "#4C1732"

st.markdown("""
<style>
.stApp {background:linear-gradient(135deg,#fff8fb 0%,#fff0f7 55%,#fde4ef 100%);color:#38152a}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#7f244c 0%,#4d1733 100%)}
[data-testid="stSidebar"] * {color:white !important}
h1,h2,h3 {color:#4c1732}
div[data-testid="stMetric"] {background:rgba(255,255,255,.9);border:1px solid #f4d2e2;padding:16px;border-radius:16px;box-shadow:0 5px 16px #d987ae20}
div.stButton>button {border-radius:12px;border:1px solid #e6a4c3;background:#d94d8c;color:white;font-weight:600}
div.stButton>button:hover {background:#a92f66;color:white;border-color:#a92f66}
div[data-testid="stForm"] {background:#fff;border:1px solid #f2d4e2;border-radius:16px;padding:16px}
</style>
""", unsafe_allow_html=True)

# ----------------------------- Conexão e acesso -----------------------------
def get_secrets():
    try:
        return (st.secrets.get("SUPABASE_URL", ""),
                st.secrets.get("SUPABASE_KEY", ""),
                st.secrets.get("APP_PASSWORD", ""),
                st.secrets.get("SI5_API_TOKEN", ""))
    except Exception:
        return "", "", "", ""

url, key, app_password, si5_token = get_secrets()
if not url or not key:
    st.title("🌸 Espaço Máximos")
    st.error("Configure SUPABASE_URL e SUPABASE_KEY nos Secrets do Streamlit.")
    st.stop()

supabase = create_client(url, key)
if app_password and not st.session_state.get("authenticated", False):
    st.markdown("<h1 style='text-align:center'>🌸 Espaço Máximos</h1><p style='text-align:center'>Perfumaria | Cosméticos | Presentes</p>", unsafe_allow_html=True)
    with st.form("login_form"):
        entered = st.text_input("Senha de acesso", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            if entered == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()

# ----------------------------- Funções gerais -----------------------------
def rows(table, order=None, desc=False):
    q = supabase.table(table).select("*")
    if order:
        q = q.order(order, desc=desc)
    return q.execute().data or []


def add_record(table, data):
    result = supabase.table(table).insert(data).execute().data or []
    return result[0] if result else None


def update_record(table, data, field, value):
    return supabase.table(table).update(data).eq(field, value).execute().data or []


def brl(value):
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def as_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_si5(term):
    if not si5_token:
        return [], "Token SI5_API_TOKEN não configurado nos Secrets."
    base = "https://global.si5.com.br/api/produtos"
    headers = {"Authorization": f"Bearer {si5_token}", "Accept": "application/json"}
    try:
        if term.isdigit() and len(term) in (8, 12, 13, 14):
            response = requests.get(f"{base}/{term}", headers=headers, timeout=15)
            if response.status_code == 404:
                response = requests.get(base, headers=headers, params={"q": term, "per_page": 20}, timeout=15)
                response.raise_for_status()
                return response.json().get("data", []), None
            response.raise_for_status()
            item = response.json()
            return ([item] if item.get("codbar") else []), None
        response = requests.get(base, headers=headers, params={"q": term, "per_page": 20}, timeout=15)
        response.raise_for_status()
        return response.json().get("data", []), None
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        return [], "Token SI5 inválido." if code == 401 else ("Limite de consultas SI5 atingido." if code == 429 else f"Erro SI5 (HTTP {code}).")
    except requests.RequestException:
        return [], "Não foi possível acessar o catálogo SI5 agora."
    except (ValueError, AttributeError):
        return [], "A resposta do catálogo SI5 veio em formato inesperado."


def upload_photo(uploaded, product_code):
    if not uploaded:
        return None
    path = f"{product_code.strip().replace('/', '-')}/{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded.name.replace(' ', '_')}"
    result = supabase.storage.from_("product-photos").upload(
        path, uploaded.getvalue(),
        file_options={"content-type": uploaded.type or "image/jpeg", "upsert": "true"}
    )
    public = supabase.storage.from_("product-photos").get_public_url(path)
    if isinstance(public, dict):
        return public.get("publicURL") or public.get("publicUrl")
    return str(public)


def get_product_lots(product_id):
    return (supabase.table("stock_lots").select("*")
            .eq("product_id", product_id).gt("quantity", 0)
            .order("expiration_date", desc=False).execute().data or [])


def consume_stock(product, quantity, sale_item_id):
    lots = get_product_lots(product["id"])
    available = sum(int(lot.get("quantity", 0) or 0) for lot in lots)
    if available < quantity:
        raise ValueError(f"Estoque insuficiente para {product['name']}. Disponível nos lotes: {available}.")
    remaining = quantity
    for lot in lots:
        if remaining <= 0:
            break
        take = min(remaining, int(lot.get("quantity", 0) or 0))
        if take:
            update_record("stock_lots", {"quantity": int(lot["quantity"]) - take}, "id", lot["id"])
            add_record("sale_lot_allocations", {"sale_item_id": sale_item_id, "stock_lot_id": lot["id"], "quantity": take})
            remaining -= take
    update_record("products", {"stock": max(0, int(product.get("stock", 0) or 0) - quantity)}, "id", product["id"])


def create_receipt_pdf(sale, items, installments):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PinkTitle", parent=styles["Title"], textColor=colors.HexColor(PINK), fontSize=21, spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallPink", parent=styles["Normal"], textColor=colors.HexColor(DARK), fontSize=9))
    story = [Paragraph("ESPAÇO MÁXIMOS", styles["PinkTitle"]), Paragraph("Perfumaria | Cosméticos | Presentes", styles["SmallPink"]), Spacer(1, 8*mm)]
    story += [Paragraph(f"<b>Comprovante de venda #{sale['id']}</b>", styles["Heading2"]),
              Paragraph(f"Cliente: {sale.get('client_name','')}<br/>Data: {sale.get('sale_date') or str(sale.get('created_at',''))[:10]}<br/>Entrega: {sale.get('delivery_status','Pendente')}", styles["Normal"]), Spacer(1, 5*mm)]
    data = [["Produto", "Qtd.", "Preço", "Desconto", "Subtotal"]]
    for item in items:
        data.append([item.get("product_name", ""), str(item.get("quantity", 0)), brl(item.get("unit_price")), brl(item.get("discount", 0)), brl(item.get("line_total"))])
    table = Table(data, colWidths=[75*mm, 15*mm, 28*mm, 28*mm, 28*mm])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor(ROSE)), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#E8B8CE")), ("FONTSIZE", (0,0), (-1,-1), 8), ("PADDING", (0,0), (-1,-1), 6)]))
    story += [table, Spacer(1, 5*mm)]
    story += [Paragraph(f"Total: <b>{brl(sale.get('total'))}</b><br/>Recebido: {brl(sale.get('paid'))}<br/>Saldo em aberto: <b>{brl(safe_float(sale.get('total'))-safe_float(sale.get('paid')))}</b><br/>Lucro estimado: {brl(sale.get('profit_estimate'))}", styles["Normal"])]
    if installments:
        story += [Spacer(1, 4*mm), Paragraph("Parcelas", styles["Heading3"])]
        p_data = [["Parcela", "Vencimento", "Valor", "Pago", "Situação"]]
        for p in installments:
            p_data.append([str(p.get("installment_number")), str(p.get("due_date")), brl(p.get("amount")), brl(p.get("paid_amount")), p.get("status", "Pendente")])
        pt = Table(p_data, colWidths=[20*mm, 32*mm, 30*mm, 30*mm, 45*mm])
        pt.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F8DCE9")), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#E8B8CE")), ("FONTSIZE", (0,0), (-1,-1), 8), ("PADDING", (0,0), (-1,-1), 5)]))
        story.append(pt)
    story += [Spacer(1, 12*mm), Paragraph("Obrigada pela preferência! 💗", styles["SmallPink"])]
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def mark_payment(sale, amount, paydate):
    balance = max(0, safe_float(sale.get("total")) - safe_float(sale.get("paid")))
    if amount <= 0 or amount > balance + 0.001:
        raise ValueError("Informe um valor positivo que não ultrapasse o saldo em aberto.")
    installments = (supabase.table("sale_installments").select("*").eq("sale_id", sale["id"]).order("installment_number").execute().data or [])
    left = float(amount)
    for inst in installments:
        if left <= 0.001:
            break
        inst_balance = max(0, safe_float(inst.get("amount")) - safe_float(inst.get("paid_amount")))
        part = min(left, inst_balance)
        if part > 0:
            new_paid_inst = safe_float(inst.get("paid_amount")) + part
            status_inst = "Pago" if new_paid_inst >= safe_float(inst.get("amount")) - 0.001 else "Parcial"
            update_record("sale_installments", {"paid_amount": new_paid_inst, "status": status_inst}, "id", inst["id"])
            left -= part
    new_paid = safe_float(sale.get("paid")) + float(amount)
    status = "Paga" if new_paid >= safe_float(sale.get("total")) - 0.001 else ("Parcial" if new_paid > 0 else "Pendente")
    update_record("sales", {"paid": new_paid, "status": status}, "id", sale["id"])
    add_record("payments", {"sale_id": sale["id"], "client_id": sale.get("client_id"), "client_name": sale.get("client_name", ""), "amount": amount, "payment_date": str(paydate)})

# ----------------------------- Dados -----------------------------
try:
    products = rows("products", "name")
    clients = rows("clients", "name")
    sales = rows("sales", "created_at", True)
    stock_lots = rows("stock_lots", "expiration_date")
    installments_all = rows("sale_installments", "due_date")
except Exception as exc:
    st.error("Não consegui carregar as tabelas novas do Espaço Máximos. Confira se a atualização SQL do projeto foi executada no Supabase.")
    st.code(str(exc))
    st.stop()

with st.sidebar:
    if os.path.exists("assets/logo_espaco_maximos.png"):
        st.image("assets/logo_espaco_maximos.png", use_container_width=True)
    st.markdown("## Espaço Máximos")
    st.caption("Perfumaria | Cosméticos | Presentes")
    page = st.radio("Menu", ["Início", "Estoque", "Vendas", "Clientes"], label_visibility="collapsed")
    st.divider()
    st.caption("Beleza, cuidado e autoestima")


def page_header(title, subtitle=""):
    st.title(title)
    if subtitle:
        st.caption(subtitle)

# -------------------------------- INÍCIO --------------------------------
if page == "Início":
    page_header("Bem-vinda ao Espaço Máximos 🌸", "Seu controle de estoque, clientes e vendas em um só lugar.")
    today = date.today()
    expiring = []
    for lot in stock_lots:
        exp = as_date(lot.get("expiration_date"))
        if exp and int(lot.get("quantity", 0) or 0) > 0 and exp <= today + timedelta(days=30):
            prod = next((p for p in products if p["id"] == lot.get("product_id")), {})
            expiring.append({"Produto": prod.get("name", "Produto"), "Quantidade": lot.get("quantity"), "Validade": exp.strftime("%d/%m/%Y"), "Situação": "Vencido" if exp < today else "Próximo do vencimento"})
    pending_deliveries = [s for s in sales if s.get("delivery_status", "Pendente") != "Entregue"]
    pending_installments = [i for i in installments_all if safe_float(i.get("amount")) - safe_float(i.get("paid_amount")) > 0.009]
    birthday_clients = []
    for c in clients:
        bday = as_date(c.get("birthday"))
        if bday:
            next_bday = bday.replace(year=today.year)
            if next_bday < today:
                next_bday = next_bday.replace(year=today.year + 1)
            if (next_bday - today).days <= 30:
                birthday_clients.append({"Cliente": c.get("name"), "Aniversário": next_bday.strftime("%d/%m"), "Telefone": c.get("phone", "")})
    due_total = sum(max(0, safe_float(i.get("amount")) - safe_float(i.get("paid_amount"))) for i in pending_installments)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Produtos a vencer", len(expiring))
    m2.metric("Entregas pendentes", len(pending_deliveries))
    m3.metric("Clientes a cobrar", len({i.get("client_id") for i in pending_installments}))
    m4.metric("Saldo a receber", brl(due_total))
    left, right = st.columns(2)
    with left:
        st.subheader("Produtos a vencer")
        if expiring:
            st.dataframe(pd.DataFrame(expiring), use_container_width=True, hide_index=True)
        else:
            st.success("Nenhum produto vencendo nos próximos 30 dias.")
        st.subheader("Entregas pendentes")
        if pending_deliveries:
            st.dataframe(pd.DataFrame([{"Venda": f"#{s['id']}", "Cliente": s.get("client_name"), "Data": s.get("sale_date"), "Situação": s.get("delivery_status", "Pendente")} for s in pending_deliveries]), use_container_width=True, hide_index=True)
        else:
            st.success("Não há entregas pendentes.")
    with right:
        st.subheader("Aniversários próximos")
        if birthday_clients:
            st.dataframe(pd.DataFrame(birthday_clients), use_container_width=True, hide_index=True)
        else:
            st.info("Cadastre as datas de aniversário na área Clientes.")
        st.subheader("Clientes a cobrar")
        if pending_installments:
            due_rows = []
            for inst in pending_installments:
                due_rows.append({"Cliente": inst.get("client_name"), "Venda": inst.get("sale_id"), "Parcela": inst.get("installment_number"), "Vencimento": inst.get("due_date"), "Em aberto": brl(safe_float(inst.get("amount"))-safe_float(inst.get("paid_amount")))})
            st.dataframe(pd.DataFrame(due_rows), use_container_width=True, hide_index=True)
        else:
            st.success("Nenhum valor pendente.")
    st.divider()
    st.subheader("Resumo de vendas")
    period = st.selectbox("Período", ["Mês atual", "Mês anterior", "Últimos 3 meses", "Últimos 6 meses", "Últimos 9 meses", "Último 1 ano"])
    start = today.replace(day=1)
    if period == "Mês anterior":
        last_day_prev = start - timedelta(days=1)
        start = last_day_prev.replace(day=1)
        end = last_day_prev
    else:
        end = today
        months = {"Últimos 3 meses":3, "Últimos 6 meses":6, "Últimos 9 meses":9, "Último 1 ano":12}
        if period in months:
            n = months[period]
            month_index = today.year * 12 + today.month - 1 - (n - 1)
            start = date(month_index // 12, month_index % 12 + 1, 1)
    selected_sales = []
    for sale in sales:
        d = as_date(sale.get("sale_date") or sale.get("created_at"))
        if d and start <= d <= end:
            selected_sales.append(sale)
    total_period = sum(safe_float(s.get("total")) for s in selected_sales)
    received_period = sum(safe_float(s.get("paid")) for s in selected_sales)
    c1, c2, c3 = st.columns(3)
    c1.metric("Vendas no período", brl(total_period))
    c2.metric("Recebido", brl(received_period))
    c3.metric("Quantidade de vendas", len(selected_sales))
    if selected_sales:
        chart_df = pd.DataFrame(selected_sales)
        chart_df["Data"] = pd.to_datetime(chart_df.apply(lambda r: r.get("sale_date") or r.get("created_at"), axis=1), errors="coerce")
        chart_df = chart_df.dropna(subset=["Data"])
        if not chart_df.empty:
            chart_df["Mês"] = chart_df["Data"].dt.to_period("M").astype(str)
            monthly = chart_df.groupby("Mês", as_index=False)["total"].sum().rename(columns={"total":"Vendas"})
            st.bar_chart(monthly, x="Mês", y="Vendas", color=PINK)
    else:
        st.info("Não há vendas nesse período.")

# -------------------------------- ESTOQUE --------------------------------
elif page == "Estoque":
    page_header("Estoque", "Cadastre produtos, fotos e lotes com datas de validade.")
    with st.expander("🔎 Buscar produto no catálogo SI5", expanded=False):
        q1, q2 = st.columns([4, 1])
        si5_term = q1.text_input("Digite o nome ou EAN", key="si5_term")
        if q2.button("Pesquisar", use_container_width=True, key="si5_btn"):
            found, error = load_si5(si5_term.strip()) if si5_term.strip() else ([], "Digite um termo para pesquisar.")
            st.session_state["si5_found"] = found
            st.session_state["si5_error"] = error or ""
        if st.session_state.get("si5_error"):
            st.warning(st.session_state["si5_error"])
        found = st.session_state.get("si5_found", [])
        if found:
            idx = st.selectbox("Resultado", range(len(found)), format_func=lambda i: f"{found[i].get('produto','Produto')} | {found[i].get('marca','')} | EAN {found[i].get('codbar','')}")
            if st.button("Usar dados no cadastro"):
                item = found[idx]
                brand_txt = str(item.get("marca") or "").upper()
                brand_value = "Natura" if "NATURA" in brand_txt else "Avon" if "AVON" in brand_txt else "O Boticário" if "BOTIC" in brand_txt else "Outra"
                st.session_state["prefill_code"] = str(item.get("codbar") or "").strip()
                st.session_state["prefill_barcode"] = str(item.get("codbar") or "").strip()
                st.session_state["prefill_brand"] = brand_value
                st.session_state["prefill_name"] = str(item.get("produto") or "")
                st.session_state["prefill_category"] = str(item.get("categoria") or "")
                st.rerun()
    with st.expander("＋ Cadastrar produto", expanded=not products):
        with st.form("product_form", clear_on_submit=True):
            a,b,c = st.columns(3)
            code = a.text_input("Código interno *", value=st.session_state.get("prefill_code", ""))
            barcode = b.text_input("Código de barras (EAN)", value=st.session_state.get("prefill_barcode", ""))
            brand = c.selectbox("Marca", ["Natura", "Avon", "O Boticário", "Outra"], index=["Natura", "Avon", "O Boticário", "Outra"].index(st.session_state.get("prefill_brand", "Outra")))
            name = st.text_input("Nome do produto *", value=st.session_state.get("prefill_name", ""))
            d,e,f = st.columns(3)
            category = d.text_input("Categoria", value=st.session_state.get("prefill_category", ""))
            cost = e.number_input("Custo unitário (R$)", min_value=0.0, step=1.0)
            price = f.number_input("Preço de venda (R$)", min_value=0.0, step=1.0)
            g,h = st.columns(2)
            initial_qty = g.number_input("Quantidade inicial", min_value=0, step=1)
            minimum = h.number_input("Estoque mínimo", min_value=0, step=1)
            expiry = st.date_input("Validade do lote inicial (opcional)", value=None)
            photo = st.file_uploader("Foto do produto (celular ou computador)", type=["png", "jpg", "jpeg", "webp"])
            save = st.form_submit_button("Salvar produto", use_container_width=True)
            if save:
                if not code.strip() or not name.strip():
                    st.error("Preencha o código e o nome do produto.")
                elif any(str(p.get("code", "")).lower() == code.strip().lower() for p in products):
                    st.error("Esse código já está cadastrado.")
                else:
                    photo_url = upload_photo(photo, code) if photo else None
                    product = add_record("products", {"code":code.strip(), "barcode":barcode.strip() or None, "brand":brand, "name":name.strip(), "category":category.strip() or None, "cost":cost, "price":price, "stock":int(initial_qty), "min_stock":int(minimum), "photo_url":photo_url})
                    if initial_qty > 0:
                        add_record("stock_lots", {"product_id":product["id"], "quantity":int(initial_qty), "expiration_date":str(expiry) if expiry else None, "unit_cost":cost, "notes":"Estoque inicial"})
                    for k in ["prefill_code", "prefill_barcode", "prefill_brand", "prefill_name", "prefill_category"]:
                        st.session_state.pop(k, None)
                    st.success("Produto cadastrado!")
                    st.rerun()
    st.subheader("＋ Entrada de estoque / novo lote")
    if products:
        with st.form("stock_entry_form"):
            product_entry = st.selectbox("Produto", products, format_func=lambda p: f"{p['code']} — {p['name']}")
            x,y,z = st.columns(3)
            entry_qty = x.number_input("Quantidade recebida", min_value=1, step=1)
            entry_cost = y.number_input("Custo por unidade (R$)", min_value=0.0, step=1.0, value=safe_float(product_entry.get("cost")))
            entry_expiry = z.date_input("Validade", value=None)
            entry_notes = st.text_input("Observação do lote")
            if st.form_submit_button("Adicionar ao estoque", use_container_width=True):
                add_record("stock_lots", {"product_id":product_entry["id"], "quantity":int(entry_qty), "expiration_date":str(entry_expiry) if entry_expiry else None, "unit_cost":entry_cost, "notes":entry_notes.strip() or None})
                update_record("products", {"stock":int(product_entry.get("stock",0))+int(entry_qty)}, "id", product_entry["id"])
                st.success("Entrada registrada!")
                st.rerun()
    else:
        st.info("Cadastre o primeiro produto para registrar entradas.")
    st.divider()
    st.subheader("Produtos cadastrados")
    if products:
        for p in products:
            with st.expander(f"{p.get('name')} | Estoque: {p.get('stock',0)} | {p.get('brand','')}"):
                if p.get("photo_url"):
                    st.image(p["photo_url"], width=150)
                st.write(f"Código: {p.get('code')} · EAN: {p.get('barcode') or '—'} · Custo: {brl(p.get('cost'))} · Venda: {brl(p.get('price'))} · Mínimo: {p.get('min_stock',0)}")
                lots = [l for l in stock_lots if l.get("product_id") == p["id"]]
                if lots:
                    st.dataframe(pd.DataFrame([{"Lote":l["id"], "Quantidade":l.get("quantity"), "Validade":l.get("expiration_date") or "Não informada", "Custo unitário":brl(l.get("unit_cost"))} for l in lots]), use_container_width=True, hide_index=True)
                with st.form(f"edit_product_{p['id']}"):
                    ep_price = st.number_input("Preço de venda", min_value=0.0, value=safe_float(p.get("price")), key=f"ep_{p['id']}")
                    ep_cost = st.number_input("Custo padrão", min_value=0.0, value=safe_float(p.get("cost")), key=f"ec_{p['id']}")
                    ep_min = st.number_input("Estoque mínimo", min_value=0, value=int(p.get("min_stock",0)), key=f"em_{p['id']}")
                    if st.form_submit_button("Atualizar produto"):
                        update_record("products", {"price":ep_price,"cost":ep_cost,"min_stock":int(ep_min)}, "id", p["id"])
                        st.success("Produto atualizado.")
                        st.rerun()
        csv = pd.DataFrame(products).to_csv(index=False).encode("utf-8-sig")
        st.download_button("Baixar estoque em CSV", csv, "estoque_espaco_maximos.csv", "text/csv")
    else:
        st.info("Ainda não há produtos cadastrados.")

# -------------------------------- CLIENTES --------------------------------
elif page == "Clientes":
    page_header("Clientes", "Cadastre contatos, aniversários e acompanhe o saldo de cada cliente.")
    with st.expander("＋ Cadastrar cliente", expanded=not clients):
        with st.form("client_form", clear_on_submit=True):
            name = st.text_input("Nome *")
            phone = st.text_input("Telefone / WhatsApp")
            birthday = st.date_input("Data de aniversário (opcional)", value=None)
            notes = st.text_area("Observações")
            if st.form_submit_button("Salvar cliente", use_container_width=True):
                if not name.strip():
                    st.error("Informe o nome do cliente.")
                else:
                    add_record("clients", {"name":name.strip(), "phone":phone.strip() or None, "birthday":str(birthday) if birthday else None, "notes":notes.strip() or None})
                    st.success("Cliente cadastrado!")
                    st.rerun()
    if clients:
        for c in clients:
            with st.expander(f"{c.get('name')} · {c.get('phone') or 'Sem telefone'}"):
                st.write(f"Aniversário: {as_date(c.get('birthday')).strftime('%d/%m/%Y') if as_date(c.get('birthday')) else 'Não informado'}")
                client_sales = [s for s in sales if s.get("client_id") == c["id"]]
                open_balance = sum(max(0, safe_float(s.get("total"))-safe_float(s.get("paid"))) for s in client_sales)
                st.metric("Saldo em aberto", brl(open_balance))
                if client_sales:
                    st.dataframe(pd.DataFrame([{"Venda":s["id"],"Data":s.get("sale_date") or str(s.get("created_at",""))[:10],"Total":brl(s.get("total")),"Pago":brl(s.get("paid")),"Saldo":brl(safe_float(s.get("total"))-safe_float(s.get("paid")))} for s in client_sales]), use_container_width=True, hide_index=True)
                with st.form(f"client_edit_{c['id']}"):
                    edit_phone = st.text_input("Telefone", value=c.get("phone") or "", key=f"cp_{c['id']}")
                    edit_bday = st.date_input("Aniversário", value=as_date(c.get("birthday")), key=f"cb_{c['id']}")
                    edit_notes = st.text_area("Observações", value=c.get("notes") or "", key=f"cn_{c['id']}")
                    if st.form_submit_button("Atualizar cadastro"):
                        update_record("clients", {"phone":edit_phone.strip() or None,"birthday":str(edit_bday) if edit_bday else None,"notes":edit_notes.strip() or None}, "id", c["id"])
                        st.success("Cadastro atualizado.")
                        st.rerun()
    else:
        st.info("Cadastre o primeiro cliente.")

# -------------------------------- VENDAS --------------------------------
elif page == "Vendas":
    page_header("Vendas", "Registre pedidos, parcelas, pagamentos e entregas.")
    with st.expander("＋ Registrar nova venda", expanded=not sales):
        if not clients or not products:
            st.warning("Cadastre ao menos um cliente e um produto antes de registrar uma venda.")
        else:
            with st.form("new_sale_form"):
                client = st.selectbox("Cliente", clients, format_func=lambda c:c["name"])
                sale_date = st.date_input("Data da venda", value=date.today())
                chosen = st.multiselect("Produtos", products, format_func=lambda p:f"{p['code']} — {p['name']} (estoque: {p.get('stock',0)})")
                lines = []
                subtotal = 0.0
                cost_total = 0.0
                for p in chosen:
                    st.markdown(f"**{p['name']}**")
                    aa,bb,cc,dd,ee = st.columns([1,1.4,1.3,1.3,1.5])
                    qty = aa.number_input("Qtd.", min_value=1, max_value=999, value=1, key=f"sale_qty_{p['id']}")
                    source = bb.selectbox("Origem", ["Tenho no estoque", "Vou encomendar"], key=f"sale_source_{p['id']}")
                    unit_price = cc.number_input("Preço unit.", min_value=0.0, value=safe_float(p.get("price")), step=1.0, key=f"sale_price_{p['id']}")
                    discount = dd.number_input("Desconto total", min_value=0.0, value=0.0, step=1.0, key=f"sale_discount_{p['id']}")
                    unit_cost = safe_float(p.get("cost"))
                    ee.write(f"Lucro estimado: {brl(max(0, unit_price*qty-discount-unit_cost*qty))}")
                    line_total = max(0, unit_price*qty-discount)
                    subtotal += line_total
                    cost_total += unit_cost*qty
                    lines.append({"product":p,"quantity":int(qty),"source":"stock" if source == "Tenho no estoque" else "order","unit_price":float(unit_price),"discount":float(discount),"unit_cost":unit_cost,"line_total":line_total})
                st.markdown(f"### Total da venda: {brl(subtotal)}")
                st.caption(f"Lucro estimado: {brl(subtotal-cost_total)}")
                received = st.number_input("Valor recebido agora (R$)", min_value=0.0, max_value=max(0.0,subtotal), step=5.0)
                n_installments = st.number_input("Quantidade de parcelas para o saldo restante", min_value=1, max_value=24, value=1, step=1)
                first_due = st.date_input("Vencimento da primeira parcela", value=date.today()+timedelta(days=30))
                delivery = st.selectbox("Situação da entrega", ["Pendente", "Entregue"])
                notes = st.text_input("Observações")
                submit_sale = st.form_submit_button("Confirmar venda", use_container_width=True)
                if submit_sale:
                    if not lines:
                        st.error("Selecione ao menos um produto.")
                    elif any(line["source"] == "stock" and line["quantity"] > int(line["product"].get("stock",0)) for line in lines):
                        st.error("Uma das quantidades é maior que o estoque disponível. Reduza a quantidade ou escolha Vou encomendar.")
                    elif received > subtotal + 0.001:
                        st.error("O valor recebido não pode ultrapassar o total.")
                    else:
                        try:
                            sale = add_record("sales", {"client_id":client["id"],"client_name":client["name"],"total":subtotal,"paid":received,"due_date":str(first_due) if subtotal-received > 0 else None,"notes":notes.strip() or None,"status":"Paga" if received >= subtotal-0.001 else ("Parcial" if received > 0 else "Pendente"),"sale_date":str(sale_date),"delivery_status":delivery,"discount":sum(l["discount"] for l in lines),"profit_estimate":subtotal-cost_total,"installments":int(n_installments)})
                            for line in lines:
                                p = line["product"]
                                item = add_record("sale_items", {"sale_id":sale["id"],"product_id":p["id"],"product_code":p["code"],"product_name":p["name"],"quantity":line["quantity"],"unit_price":line["unit_price"],"line_total":line["line_total"],"unit_cost":line["unit_cost"],"discount":line["discount"],"source":line["source"]})
                                if line["source"] == "stock":
                                    consume_stock(p, line["quantity"], item["id"])
                            remaining = max(0.0, subtotal-float(received))
                            if remaining > 0.001:
                                part = round(remaining/int(n_installments), 2)
                                distributed = 0.0
                                for number in range(1, int(n_installments)+1):
                                    amount = round(remaining-distributed,2) if number == int(n_installments) else part
                                    distributed += amount
                                    due_date = first_due + timedelta(days=30*(number-1))
                                    add_record("sale_installments", {"sale_id":sale["id"],"client_id":client["id"],"client_name":client["name"],"installment_number":number,"due_date":str(due_date),"amount":amount,"paid_amount":0,"status":"Pendente"})
                            if received > 0:
                                add_record("payments", {"sale_id":sale["id"],"client_id":client["id"],"client_name":client["name"],"amount":received,"payment_date":str(sale_date)})
                            st.success(f"Venda #{sale['id']} registrada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível concluir a venda: {exc}")
    st.divider()
    st.subheader("Histórico de vendas")
    if sales:
        for s in sales:
            with st.expander(f"Venda #{s['id']} · {s.get('client_name','')} · {brl(s.get('total'))} · {s.get('status','')}"):
                items = supabase.table("sale_items").select("*").eq("sale_id",s["id"]).execute().data or []
                insts = supabase.table("sale_installments").select("*").eq("sale_id",s["id"]).order("installment_number").execute().data or []
                st.write(f"Data: {s.get('sale_date') or str(s.get('created_at',''))[:10]} · Total: {brl(s.get('total'))} · Pago: {brl(s.get('paid'))} · Em aberto: {brl(safe_float(s.get('total'))-safe_float(s.get('paid')))}")
                st.write(f"Lucro estimado: {brl(s.get('profit_estimate'))} · Entrega: {s.get('delivery_status','Pendente')}")
                for item in items:
                    source_label = "Estoque" if item.get("source", "stock") == "stock" else "Encomenda"
                    st.write(f"{item.get('quantity')} × {item.get('product_name')} · {brl(item.get('line_total'))} · {source_label}")
                if insts:
                    st.dataframe(pd.DataFrame([{"Parcela":i.get("installment_number"),"Vencimento":i.get("due_date"),"Valor":brl(i.get("amount")),"Pago":brl(i.get("paid_amount")),"Situação":i.get("status")} for i in insts]), use_container_width=True, hide_index=True)
                col1,col2 = st.columns(2)
                if s.get("delivery_status", "Pendente") != "Entregue":
                    if col1.button("Marcar como entregue", key=f"deliver_{s['id']}"):
                        update_record("sales", {"delivery_status":"Entregue"}, "id", s["id"])
                        st.success("Entrega atualizada.")
                        st.rerun()
                else:
                    col1.success("Entrega concluída")
                balance = max(0, safe_float(s.get("total"))-safe_float(s.get("paid")))
                if balance > 0.001:
                    with st.form(f"payment_form_{s['id']}"):
                        amount = st.number_input("Registrar recebimento (R$)", min_value=0.01, max_value=balance, step=5.0, key=f"payment_amount_{s['id']}")
                        paydate = st.date_input("Data do recebimento", value=date.today(), key=f"payment_date_{s['id']}")
                        if st.form_submit_button("Registrar pagamento"):
                            try:
                                mark_payment(s, amount, paydate)
                                st.success("Pagamento registrado!")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                try:
                    pdf = create_receipt_pdf(s, items, insts)
                    col2.download_button("Baixar comprovante em PDF", pdf, f"comprovante_venda_{s['id']}.pdf", "application/pdf", key=f"pdf_{s['id']}")
                except Exception as exc:
                    st.warning(f"Não foi possível gerar o PDF: {exc}. Confira se reportlab está no requirements.txt.")
    else:
        st.info("Nenhuma venda registrada ainda.")
