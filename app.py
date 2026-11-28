import streamlit as st
from supabase import create_client
from datetime import date, datetime
import pandas as pd
import os
import requests

st.set_page_config(page_title="Espaço Máximos | Estoque & Vendas", page_icon="🌸", layout="wide")

PINK = "#D94D8C"
ROSE = "#A92F66"
BLUSH = "#FFF1F7"
DARK = "#4C1732"

st.markdown("""
<style>
.stApp { background: linear-gradient(135deg,#fff8fb 0%,#fff0f7 55%,#fde4ef 100%); color:#38152a; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#7f244c 0%,#4d1733 100%); }
[data-testid="stSidebar"] * { color: white !important; }
h1,h2,h3 { color:#4c1732; }
div[data-testid="stMetric"] { background:rgba(255,255,255,.88); border:1px solid #f4d2e2; padding:18px; border-radius:18px; box-shadow:0 5px 16px #d987ae20; }
div.stButton > button { border-radius:12px; border:1px solid #e6a4c3; background:#d94d8c; color:white; font-weight:600; }
div.stButton > button:hover { background:#a92f66; color:white; border-color:#a92f66; }
div[data-testid="stForm"] { background:#fff; border:1px solid #f2d4e2; border-radius:16px; padding:18px; }
</style>
""", unsafe_allow_html=True)

def get_secrets():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        password = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        url, key, password = "", "", ""
    return url, key, password

url, key, app_password = get_secrets()
if not url or not key:
    st.title("🌸 Espaço Máximos")
    st.info("O projeto está criado! Para conectar o banco online, configure o Supabase e adicione SUPABASE_URL e SUPABASE_KEY nos Secrets do Streamlit.")
    st.markdown("### Próximo passo")
    st.markdown("1. Crie um projeto gratuito no [Supabase](https://supabase.com/).")
    st.markdown("2. Execute o arquivo `supabase_schema.sql` no SQL Editor do Supabase.")
    st.markdown("3. Em Streamlit Cloud, abra **Settings → Secrets** e preencha os dados do arquivo `.streamlit/secrets.toml.example`.")
    st.stop()

supabase = create_client(url, key)

# Simple private entry gate. Set APP_PASSWORD in Streamlit Secrets.
if app_password:
    if not st.session_state.get("authenticated", False):
        st.markdown("<h1 style='text-align:center'>Espaço Máximos</h1><p style='text-align:center'>Perfumaria | Cosméticos | Presentes</p>", unsafe_allow_html=True)
        with st.form("login"):
            entered = st.text_input("Senha de acesso", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            if submitted:
                if entered == app_password:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
        st.stop()

def rows(table, order=None):
    q = supabase.table(table).select("*")
    if order:
        q = q.order(order, desc=True)
    return q.execute().data or []

def add_record(table, data):
    return supabase.table(table).insert(data).execute().data

def update_record(table, data, field, value):
    return supabase.table(table).update(data).eq(field, value).execute().data

def brl(value):
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

with st.sidebar:
    if os.path.exists("assets/logo_espaco_maximos.png"):
        st.image("assets/logo_espaco_maximos.png", use_container_width=True)
    st.markdown("## Espaço Máximos")
    st.caption("Perfumaria | Cosméticos | Presentes")
    page = st.radio("Menu", ["Início", "Produtos", "Clientes", "Nova venda", "Vendas", "Contas a receber", "Relatórios"], label_visibility="collapsed")
    st.divider()
    st.caption("Beleza, cuidado e autoestima")

products = rows("products", "name")
clients = rows("clients", "name")
sales = rows("sales", "created_at")

def page_header(title, subtitle=""):
    st.title(title)
    if subtitle:
        st.caption(subtitle)

if page == "Início":
    page_header("Bem-vinda ao Espaço Máximos 🌸", "Seu controle de estoque e vendas em um só lugar.")
    total_stock = sum(int(p.get("stock",0) or 0) for p in products)
    month = date.today().strftime("%Y-%m")
    monthly = [s for s in sales if str(s.get("created_at",""))[:7] == month]
    month_total = sum(float(s.get("total",0) or 0) for s in monthly)
    receivable = sum(max(0, float(s.get("total",0) or 0)-float(s.get("paid",0) or 0)) for s in sales)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Produtos cadastrados", len(products))
    c2.metric("Unidades em estoque", total_stock)
    c3.metric("Vendas no mês", brl(month_total))
    c4.metric("A receber", brl(receivable))
    st.markdown("### Acesso rápido")
    a,b,c = st.columns(3)
    if a.button("+ Novo produto", use_container_width=True): st.session_state["go_products"] = True
    if b.button("ðŸ›’ Registrar venda", use_container_width=True): st.session_state["go_sale"] = True
    if c.button("ðŸ‘¤ Cadastrar cliente", use_container_width=True): st.session_state["go_clients"] = True
    if st.session_state.pop("go_products",False): st.info("Abra Produtos no menu para cadastrar.")
    if st.session_state.pop("go_sale",False): st.info("Abra Nova venda no menu para registrar.")
    if st.session_state.pop("go_clients",False): st.info("Abra Clientes no menu para cadastrar.")
    st.markdown("### Vendas recentes")
    if sales:
        df = pd.DataFrame(sales[:10])
        cols = [c for c in ["created_at","client_name","total","paid","status"] if c in df.columns]
        if cols:
            df = df[cols].rename(columns={"created_at":"Data","client_name":"Cliente","total":"Total","paid":"Pago","status":"Situação"})
            st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Suas vendas aparecerão aqui depois que você registrar a primeira.")



elif page == "Produtos":
    page_header("Produtos", "Pesquise no catálogo ou cadastre seus produtos.")

    def consultar_si5(termo):
        token = st.secrets.get("SI5_API_TOKEN", "")
        if not token:
            return [], "Token SI5 não configurado nos Secrets do Streamlit."

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        base = "https://global.si5.com.br/api/produtos"

        try:
            if termo.isdigit() and len(termo) in (8, 12, 13, 14):
                response = requests.get(
                    f"{base}/{termo}",
                    headers=headers,
                    timeout=12
                )
                if response.status_code == 404:
                    response = requests.get(
                        base,
                        headers=headers,
                        params={"q": termo, "per_page": 20},
                        timeout=12
                    )
                    response.raise_for_status()
                    return response.json().get("data", []), None

                response.raise_for_status()
                item = response.json()
                return ([item] if item.get("codbar") else []), None

            response = requests.get(
                base,
                headers=headers,
                params={"q": termo, "per_page": 20},
                timeout=12
            )
            response.raise_for_status()
            return response.json().get("data", []), None

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 401:
                return [], "Token inválido. Confira os Secrets do Streamlit."
            if status == 429:
                return [], "Limite diário de consultas atingido. Tente novamente amanhã."
            return [], f"Erro na consulta ao catálogo (HTTP {status})."
        except requests.RequestException:
            return [], "Não foi possível acessar o catálogo. Confira sua conexão e tente novamente."
        except (ValueError, AttributeError):
            return [], "A resposta do catálogo veio em formato inesperado."

    st.markdown("### 🔎 Buscar produto no catálogo")
    st.caption("Pesquise pelo código de barras (EAN) ou pelo nome. A consulta inclui Natura, Avon, O Boticário e outras marcas disponíveis na base.")

    busca_col, botao_col = st.columns([4, 1])
    termo = busca_col.text_input(
        "Digite o EAN ou nome do produto",
        key="si5_query"
    )
    pesquisar = botao_col.button(
        "Pesquisar",
        use_container_width=True,
        key="si5_search_button"
    )

    if pesquisar:
        st.session_state.pop("si5_selected_index", None)
        st.session_state["si5_results"] = []
        st.session_state["si5_error"] = ""

        if not termo.strip():
            st.session_state["si5_error"] = "Digite um EAN ou nome para pesquisar."
        else:
            resultados, erro = consultar_si5(termo.strip())
            st.session_state["si5_results"] = resultados
            st.session_state["si5_error"] = erro or ""

    if st.session_state.get("si5_error"):
        st.warning(st.session_state["si5_error"])

    resultados = st.session_state.get("si5_results", [])

    if resultados:
        st.success(f"{len(resultados)} resultado(s) encontrado(s).")

        selecionado = st.selectbox(
            "Escolha o produto encontrado",
            options=range(len(resultados)),
            format_func=lambda i: (
                f'{resultados[i].get("produto", "Sem nome")} | '
                f'{resultados[i].get("marca") or "Marca não informada"} | '
                f'EAN: {resultados[i].get("codbar") or "Não informado"}'
            ),
            key="si5_selected_index"
        )

        if st.button("Usar dados deste produto no cadastro", key="si5_use_product"):
            produto = resultados[selecionado]
            marca_api = str(produto.get("marca") or "").upper()

            if "NATURA" in marca_api:
                marca_final = "Natura"
            elif "AVON" in marca_api:
                marca_final = "Avon"
            elif "BOTIC" in marca_api:
                marca_final = "O Boticário"
            else:
                marca_final = "Outra"

            ean = str(produto.get("codbar") or "").strip()

            st.session_state["product_code"] = ean
            st.session_state["product_barcode"] = ean
            st.session_state["product_brand"] = marca_final
            st.session_state["product_name"] = str(produto.get("produto") or "")
            st.session_state["product_category"] = str(produto.get("categoria") or "")

            st.rerun()

    elif pesquisar and not st.session_state.get("si5_error"):
        st.info("Nenhum produto encontrado. Você pode fazer o cadastro manual abaixo.")

    st.divider()

    with st.expander("+ Cadastrar produto", expanded=True):
        with st.form("new_product", clear_on_submit=True):
            x1, x2, x3 = st.columns(3)
            code = x1.text_input(
                "Código interno / catálogo *",
                key="product_code"
            )
            barcode = x2.text_input(
                "Código de barras (EAN)",
                key="product_barcode"
            )
            brand = x3.selectbox(
                "Marca",
                ["Natura", "Avon", "O Boticário", "Outra"],
                key="product_brand"
            )

            name = st.text_input("Nome do produto *", key="product_name")

            x4, x5, x6 = st.columns(3)
            category = x4.text_input("Categoria", key="product_category")
            cost = x5.number_input("Custo (R$)", min_value=0.0, step=1.0)
            price = x6.number_input("Preço de venda (R$)", min_value=0.0, step=1.0)

            x7, x8 = st.columns(2)
            stock = x7.number_input("Estoque inicial", min_value=0, step=1)
            minimum = x8.number_input("Estoque mínimo", min_value=0, step=1)

            save = st.form_submit_button("Salvar produto", use_container_width=True)

            if save:
                if not code.strip() or not name.strip():
                    st.error("Preencha o código e o nome do produto.")
                elif any(str(p.get("code", "")).strip().lower() == code.strip().lower() for p in products):
                    st.error("Esse código já está cadastrado.")
                elif barcode.strip() and any(str(p.get("barcode", "")).strip() == barcode.strip() for p in products):
                    st.error("Esse EAN já está cadastrado.")
                else:
                    add_record("products", {
                        "code": code.strip(),
                        "barcode": barcode.strip(),
                        "brand": brand,
                        "name": name.strip(),
                        "category": category.strip(),
                        "cost": cost,
                        "price": price,
                        "stock": int(stock),
                        "min_stock": int(minimum)
                    })
                    st.success("Produto cadastrado!")
                    st.rerun()

    if products:
        df = pd.DataFrame(products)
        show = [c for c in ["code", "barcode", "brand", "name", "category", "cost", "price", "stock", "min_stock"] if c in df.columns]
        st.dataframe(
            df[show].rename(columns={
                "code": "Código",
                "barcode": "EAN",
                "brand": "Marca",
                "name": "Produto",
                "category": "Categoria",
                "cost": "Custo",
                "price": "Preço",
                "stock": "Estoque",
                "min_stock": "Mínimo"
            }),
            use_container_width=True,
            hide_index=True
        )
        csv = df[show].to_csv(index=False).encode("utf-8-sig")
        st.download_button("Baixar produtos em CSV", csv, "produtos_espaco_maximos.csv", "text/csv")
    else:
        st.info("Ainda não há produtos cadastrados.")

elif page == "Clientes":
    page_header("Clientes", "Cadastre seus clientes e acompanhe as compras.")
    with st.expander("+ Cadastrar cliente", expanded=True):
        with st.form("new_client", clear_on_submit=True):
            name = st.text_input("Nome *")
            phone = st.text_input("Telefone / WhatsApp")
            notes = st.text_area("Observações")
            save = st.form_submit_button("Salvar cliente", use_container_width=True)
            if save:
                if not name.strip(): st.error("Informe o nome.")
                else:
                    add_record("clients", {"name":name.strip(),"phone":phone.strip(),"notes":notes.strip()})
                    st.success("Cliente cadastrado!")
                    st.rerun()
    if clients:
        st.dataframe(pd.DataFrame(clients).rename(columns={"name":"Cliente","phone":"Telefone","notes":"Observações"}), use_container_width=True, hide_index=True)
    else: st.info("Cadastre o primeiro cliente.")

elif page == "Nova venda":
    page_header("Nova venda", "Selecione o cliente, os produtos e registre o pagamento.")
    if not clients or not products:
        st.warning("Cadastre pelo menos um cliente e um produto antes de registrar uma venda.")
    else:
        with st.form("sale_form"):
            client = st.selectbox("Cliente", clients, format_func=lambda c: c["name"])
            chosen = st.multiselect("Produtos", products, format_func=lambda p: f'{p["code"]} — {p["name"]} (estoque {p["stock"]})')
            qtys = {}
            for p in chosen:
                qtys[p["id"]] = st.number_input(f'Quantidade — {p["name"]}', min_value=1, max_value=max(1,int(p.get("stock",0))), value=1, key=f'q_{p["id"]}')
            paid = st.number_input("Valor recebido agora (R$)", min_value=0.0, step=5.0)
            due = st.date_input("Vencimento (se ficar saldo)", value=date.today())
            notes = st.text_input("Observação")
            total = sum(float(p["price"])*int(qtys.get(p["id"],1)) for p in chosen)
            st.markdown(f"### Total: {brl(total)}")
            submit = st.form_submit_button("Confirmar venda e baixar estoque", use_container_width=True)
            if submit:
                if not chosen: st.error("Selecione ao menos um produto.")
                elif any(int(qtys[p["id"]]) > int(p.get("stock",0)) for p in chosen): st.error("Quantidade maior que o estoque.")
                elif paid > total: st.error("O valor recebido não pode ser maior que o total.")
                else:
                    sale_data = {"client_id":client["id"],"client_name":client["name"],"total":total,"paid":paid,"due_date":str(due),"notes":notes,"status":"Paga" if paid >= total else ("Parcial" if paid > 0 else "Pendente")}
                    created = add_record("sales", sale_data)[0]
                    for p in chosen:
                        qty = int(qtys[p["id"]])
                        add_record("sale_items", {"sale_id":created["id"],"product_id":p["id"],"product_code":p["code"],"product_name":p["name"],"quantity":qty,"unit_price":p["price"],"line_total":float(p["price"])*qty})
                        update_record("products", {"stock":int(p.get("stock",0))-qty}, "id", p["id"])
                    st.success(f"Venda registrada! Saldo pendente: {brl(total-paid)}")
                    st.session_state["last_sale"] = created["id"]
                    st.rerun()
    if st.session_state.get("last_sale"):
        st.info(f'Ãšltima venda registrada: #{st.session_state["last_sale"]}')

elif page == "Vendas":
    page_header("Vendas", "Histórico de vendas e comprovantes.")
    if sales:
        for s in sales:
            with st.expander(f'Venda #{s["id"]} Â· {s.get("client_name","")} Â· {brl(s.get("total",0))} Â· {s.get("status","")}'):
                items = supabase.table("sale_items").select("*").eq("sale_id",s["id"]).execute().data or []
                st.write(f'Data: {str(s.get("created_at",""))[:10]}')
                for item in items:
                    st.write(f'{item["quantity"]} Ã— {item["product_name"]} — {brl(item["line_total"])}')
                st.write(f'Total: {brl(s["total"])} | Pago: {brl(s["paid"])} | Em aberto: {brl(float(s["total"])-float(s["paid"]))}')
                st.caption(f'Vencimento: {s.get("due_date","—")}')
                receipt = f'ESPAÃ‡O MÃXIMOS\\nComprovante de venda #{s["id"]}\\nCliente: {s.get("client_name","")}\\n' + "\\n".join([f'{i["quantity"]} x {i["product_name"]} = {brl(i["line_total"])}' for i in items]) + f'\\nTotal: {brl(s["total"])}\\nPago: {brl(s["paid"])}\\nEm aberto: {brl(float(s["total"])-float(s["paid"]))}'
                st.download_button("Baixar comprovante TXT", receipt, f"comprovante_{s['id']}.txt", key=f"receipt_{s['id']}")
    else: st.info("Nenhuma venda registrada ainda.")

elif page == "Contas a receber":
    page_header("Contas a receber", "Registre pagamentos parciais e acompanhe saldos.")
    pending = [s for s in sales if float(s.get("total",0))-float(s.get("paid",0)) > 0.001]
    if pending:
        for s in pending:
            balance = float(s["total"])-float(s["paid"])
            with st.expander(f'{s.get("client_name","")} Â· Venda #{s["id"]} Â· Em aberto {brl(balance)}'):
                st.write(f'Total: {brl(s["total"])} | Já pago: {brl(s["paid"])} | Saldo: {brl(balance)}')
                with st.form(f'payment_{s["id"]}'):
                    amount = st.number_input("Valor recebido (R$)", min_value=0.01, max_value=balance, step=5.0, key=f'amount_{s["id"]}')
                    paydate = st.date_input("Data do pagamento", value=date.today(), key=f'date_{s["id"]}')
                    submit = st.form_submit_button("Registrar pagamento")
                    if submit:
                        new_paid = float(s["paid"])+float(amount)
                        status = "Paga" if new_paid >= float(s["total"])-0.001 else "Parcial"
                        update_record("sales", {"paid":new_paid,"status":status}, "id", s["id"])
                        add_record("payments", {"sale_id":s["id"],"client_id":s["client_id"],"client_name":s["client_name"],"amount":amount,"payment_date":str(paydate)})
                        st.success("Pagamento registrado!")
                        st.rerun()
    else: st.success("Não há valores pendentes ðŸŽ‰")

elif page == "Relatórios":
    page_header("Relatórios", "Resumo para acompanhar sua revenda.")
    c1,c2 = st.columns(2)
    c1.metric("Vendas acumuladas", brl(sum(float(s.get("total",0) or 0) for s in sales)))
    c2.metric("Recebido", brl(sum(float(s.get("paid",0) or 0) for s in sales)))
    if sales:
        df = pd.DataFrame(sales)
        if "created_at" in df:
            df["Mês"] = df["created_at"].astype(str).str[:7]
            monthly = df.groupby("Mês",as_index=False)["total"].sum().rename(columns={"total":"Vendas"})
            st.bar_chart(monthly, x="Mês", y="Vendas", color=PINK)