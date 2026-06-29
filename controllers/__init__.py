"""
controllers/__init__.py — Blueprints Flask separados por domínio.

ClienteController  → rotas do cliente  (/cadastro, /login, /agendar, …)
AdminController    → rotas do admin    (/admin/…)
"""
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash
)
from functools import wraps
from models import (
    Cliente, Tema, TemaItem, TemaImagem, Disponibilidade,
    Agendamento, AgendamentoItemExtra, Reagendamento, Pagamento, Entrega, FormaPagamento,
    StatusAgendamento, StatusPagamento, EntregaRetirada, StatusDisponibilidade,
    PRECO_ITEM_EXTRA, MAX_QTD_ITEM_EXTRA, TAXA_REAGENDAMENTO,
)

# ── credenciais admin (produção: use env vars) ──
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"


# ═══════════════════════════════════════════════════════════
#  DECORATORS
# ═══════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "cliente_id" not in session:
            return redirect(url_for("cliente.index"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def _cliente_atual() -> Cliente:
    return Cliente.buscar_por_id(session["cliente_id"])


# ═══════════════════════════════════════════════════════════
#  CLIENTE BLUEPRINT
# ═══════════════════════════════════════════════════════════

cliente_bp = Blueprint("cliente", __name__)


@cliente_bp.route("/")
def index():
    if "cliente_id" in session:
        return redirect(url_for("cliente.menu"))
    return render_template("cliente/index.html")


# ── Auth ──

@cliente_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        try:
            cli = Cliente.criar(
                nome      = request.form.get("nome", ""),
                email     = request.form.get("email", ""),
                cpf       = request.form.get("cpf", ""),
                cep       = request.form.get("cep", ""),
                senha     = request.form.get("senha", ""),
                telefone  = request.form.get("telefone") or None,
                endereco  = request.form.get("endereco") or None,
            )
            cli.salvar()
            session["cliente_id"]   = cli.id
            session["cliente_nome"] = cli.nome
            flash(f"Bem-vindo(a), {cli.nome}! Cadastro realizado com sucesso! 🎉", "sucesso")
            return redirect(url_for("cliente.menu"))
        except ValueError as e:
            for msg in e.args[0]:
                flash(msg, "erro")
    return render_template("cliente/cadastro.html")


@cliente_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        cli   = Cliente.buscar_por_email(email)
        if cli and cli.verificar_senha(senha):
            session["cliente_id"]   = cli.id
            session["cliente_nome"] = cli.nome
            flash(f"Olá, {cli.nome}! Bem-vindo(a) de volta! 🎊", "sucesso")
            return redirect(url_for("cliente.menu"))
        flash("E-mail ou senha incorretos.", "erro")
    return render_template("cliente/login.html")


@cliente_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("cliente.index"))


# ── Menu principal ──

@cliente_bp.route("/menu")
@login_required
def menu():
    return render_template("cliente/menu.html")


# ── Agendamentos ──

@cliente_bp.route("/meus-agendamentos")
@login_required
def meus_agendamentos():
    """
    Lista agendamentos ativos do cliente — aba 'Temas reservados'.
    Filtra por status via ?filtro=ativo|cancelado|todos
    """
    from datetime import date, timedelta

    filtro = request.args.get("filtro", "ativo")
    ags_raw = Agendamento.listar_por_cliente(session["cliente_id"])

    hoje = date.today()
    agendamentos = []
    for ag in ags_raw:
        if filtro == "ativo"    and ag.status not in [StatusAgendamento.PENDENTE, StatusAgendamento.CONCLUIDO]:
            continue
        if filtro == "cancelado" and ag.status != StatusAgendamento.CANCELADO:
            continue
        # Adiciona prazo de cancelamento
        try:
            ev = date.fromisoformat(ag.data_evento)
            prazo_canc = ev - timedelta(days=2)
            ag._prazo_canc_ok  = hoje <= prazo_canc
            ag._prazo_canc_fmt = prazo_canc.strftime("%d/%m/%Y")
        except Exception:
            ag._prazo_canc_ok  = False
            ag._prazo_canc_fmt = "—"
        agendamentos.append(ag)

    return render_template("cliente/meus_agendamentos.html",
                           agendamentos=agendamentos, filtro=filtro)


# ── TELA 1: Catálogo de temas (listagem) ──

@cliente_bp.route("/agendar")
@login_required
def agendar():
    """Listagem de temas disponíveis — filtro A=disponíveis / B=já alugados pelo cliente."""
    filtro = request.args.get("filtro", "A")   # A=Alugar  B=Já alugados

    temas = Tema.listar_ativos()

    # IDs de temas que o cliente já agendou (para filtro B)
    from database import Database as _DB
    conn = _DB.connect()
    alugados_ids = {
        r["tema_id"] for r in conn.execute(
            "SELECT DISTINCT tema_id FROM agendamentos WHERE cliente_id=? AND status!='Cancelado'",
            (session["cliente_id"],),
        ).fetchall()
    }
    conn.close()

    if filtro == "B":
        temas = [t for t in temas if t.id in alugados_ids]
    else:
        temas = [t for t in temas if t.id not in alugados_ids]

    return render_template("cliente/catalogo.html", temas=temas, filtro=filtro,
                           alugados_ids=alugados_ids)


# ── TELA 2: Detalhes do tema ──

@cliente_bp.route("/agendar/<int:tema_id>", methods=["GET", "POST"])
@login_required
def agendar_tema(tema_id):
    """Detalhes do tema com seleção de data e confirmação."""
    tema = Tema.buscar_por_id(tema_id)
    if not tema or not tema.ativo:
        flash("Tema não encontrado.", "erro")
        return redirect(url_for("cliente.agendar"))

    datas       = Disponibilidade.listar_livres()
    itens       = tema.carregar_itens()
    imagens     = tema.carregar_imagens()
    outros_temas= Tema.listar_ativos()
    temas_json  = [t.to_dict() for t in outros_temas]

    if request.method == "POST":
        data_evento      = request.form.get("data_evento", "")
        entrega_retirada = request.form.get("entrega_retirada", EntregaRetirada.RETIRADA)
        observacoes      = request.form.get("observacoes", "").strip()

        if not data_evento:
            flash("Selecione uma data para continuar.", "erro")
            return render_template("cliente/tema_detalhe.html", tema=tema, datas=datas, itens=itens, imagens=imagens, temas_json=temas_json)

        disp = Disponibilidade.buscar_por_data(data_evento)
        if not disp or disp.status != StatusDisponibilidade.LIVRE:
            flash("Esta data não está mais disponível. Escolha outra.", "erro")
            return render_template("cliente/tema_detalhe.html", tema=tema, datas=datas, itens=itens, imagens=imagens, temas_json=temas_json)

        # Dados de entrega (obrigatório se escolheu Entrega)
        entrega_horario  = request.form.get("entrega_horario", "").strip()
        entrega_endereco = request.form.get("entrega_endereco", "").strip()
        entrega_obs      = request.form.get("entrega_obs", "").strip()

        if entrega_retirada == EntregaRetirada.ENTREGA:
            if not entrega_horario:
                flash("Horário de entrega é obrigatório.", "erro")
                return render_template("cliente/tema_detalhe.html", tema=tema, datas=datas, itens=itens, imagens=imagens, temas_json=temas_json)
            if not entrega_endereco:
                flash("Endereço de entrega é obrigatório.", "erro")
                return render_template("cliente/tema_detalhe.html", tema=tema, datas=datas, itens=itens, imagens=imagens, temas_json=temas_json)

        # Itens extras de outros temas
        extra_tema_ids  = request.form.getlist("extra_tema_id[]")
        extra_item_nomes= request.form.getlist("extra_item_nome[]")
        extra_qtds      = request.form.getlist("extra_qtd[]")
        extras_validos  = []
        valor_extras    = 0.0
        for tid_s, nome_item, qtd_s in zip(extra_tema_ids, extra_item_nomes, extra_qtds):
            nome_item = nome_item.strip()
            if not nome_item or not tid_s:
                continue
            try:
                qtd = max(1, min(int(qtd_s or 1), MAX_QTD_ITEM_EXTRA))
            except (ValueError, TypeError):
                qtd = 1
            t_extra = Tema.buscar_por_id(int(tid_s))
            if t_extra:
                extras_validos.append((t_extra, nome_item, qtd))
                valor_extras += qtd * PRECO_ITEM_EXTRA

        valor_total = tema.valor + round(valor_extras, 2)

        # Cria agendamento com pagamento Pendente
        ag = Agendamento(
            id               = None,
            cliente_id       = session["cliente_id"],
            tema_id          = tema.id,
            tema_nome        = tema.nome,
            data_evento      = data_evento,
            valor_total      = valor_total,
            entrega_retirada = entrega_retirada,
            observacoes      = observacoes,
        )
        ag.salvar()  # cria pagamento Pendente automaticamente

        # Salva itens extras
        for t_extra, nome_item, qtd in extras_validos:
            AgendamentoItemExtra(
                None, ag.id, t_extra.id, t_extra.nome, nome_item, qtd
            ).salvar()

        # Atualiza valor do pagamento
        pag = Pagamento.buscar_por_agendamento(ag.id)
        if pag and valor_total != tema.valor:
            pag.valor = valor_total
            pag.salvar()

        # Salva dados de entrega
        if entrega_retirada == EntregaRetirada.ENTREGA:
            Entrega(None, ag.id, entrega_horario, entrega_endereco, entrega_obs or None).salvar()

        flash(f"Festa {tema.emoji} reservada para {disp.data_br}! Agora realize o pagamento.", "sucesso")
        return redirect(url_for("cliente.meu_pagamento", ag_id=ag.id))

    return render_template("cliente/tema_detalhe.html", tema=tema, datas=datas, itens=itens, imagens=imagens, temas_json=temas_json)


# ── Seção de Pagamento do agendamento ──

@cliente_bp.route("/meu-pagamento/<int:ag_id>")
@login_required
def meu_pagamento(ag_id):
    """Página de pagamento de um agendamento específico."""
    ag = Agendamento.buscar_por_id(ag_id)
    if not ag or ag.cliente_id != session["cliente_id"]:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    pag     = Pagamento.buscar_por_agendamento(ag_id)
    entrega = Entrega.buscar_por_agendamento(ag_id)
    tema    = Tema.buscar_por_id(ag.tema_id)
    fps     = FormaPagamento.listar_ativas()

    # Calcula prazo: até 2 dias antes do evento
    from datetime import date, timedelta
    data_evento = date.fromisoformat(ag.data_evento)
    prazo_pag   = data_evento - timedelta(days=2)
    hoje        = date.today()
    prazo_ok    = hoje <= prazo_pag
    dias_restantes = (prazo_pag - hoje).days

    return render_template(
        "cliente/meu_pagamento.html",
        ag=ag, pag=pag, entrega=entrega, tema=tema, fps=fps,
        prazo_pag=prazo_pag.strftime("%d/%m/%Y"),
        prazo_ok=prazo_ok,
        dias_restantes=dias_restantes,
    )


@cliente_bp.route("/meu-pagamento/<int:ag_id>/pagar", methods=["POST"])
@login_required
def realizar_pagamento(ag_id):
    """Processa o pagamento de um agendamento pendente."""
    ag = Agendamento.buscar_por_id(ag_id)
    if not ag or ag.cliente_id != session["cliente_id"]:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    pag = Pagamento.buscar_por_agendamento(ag_id)
    if not pag or pag.status == StatusPagamento.PAGO:
        flash("Pagamento já realizado ou não disponível.", "erro")
        return redirect(url_for("cliente.meu_pagamento", ag_id=ag_id))

    # Verifica prazo
    from datetime import date, timedelta
    prazo = date.fromisoformat(ag.data_evento) - timedelta(days=2)
    if date.today() > prazo:
        flash("O prazo para pagamento expirou (até 2 dias antes do evento).", "erro")
        return redirect(url_for("cliente.meu_pagamento", ag_id=ag_id))

    forma_id = request.form.get("forma_pagamento_id", "")
    if not forma_id:
        flash("Selecione uma forma de pagamento.", "erro")
        return redirect(url_for("cliente.meu_pagamento", ag_id=ag_id))

    fp = FormaPagamento.buscar_por_id(int(forma_id))
    forma_nome = fp.nome if fp else "Outro"
    pag.marcar_pago(forma_nome)

    flash(f"Pagamento de R$ {ag.valor_total:,.2f} confirmado via {forma_nome}! 🎉", "sucesso")
    return redirect(url_for("cliente.meu_pagamento", ag_id=ag_id))


# ── Lista de pagamentos do cliente ──

@cliente_bp.route("/meus-pagamentos")
@login_required
def meus_pagamentos():
    """Seção de todos os pagamentos do cliente."""
    from database import Database
    from datetime import date, timedelta
    conn = Database.connect()
    rows = conn.execute(
        """SELECT a.id as ag_id, a.data_evento, a.tema_nome, a.valor_total,
                  a.entrega_retirada, a.status as ag_status,
                  p.id as pag_id, p.status as pag_status,
                  p.forma_pagamento, p.valor_reembolso
           FROM agendamentos a
           LEFT JOIN pagamentos p ON p.agendamento_id = a.id
           WHERE a.cliente_id = ?
           ORDER BY a.criado_em DESC""",
        (session["cliente_id"],),
    ).fetchall()
    conn.close()

    hoje = date.today()
    pagamentos = []
    for r in rows:
        d = dict(r)
        try:
            ev = date.fromisoformat(d["data_evento"])
            prazo = ev - timedelta(days=2)
            d["prazo_pag"]    = prazo.strftime("%d/%m/%Y")
            d["prazo_ok"]     = hoje <= prazo
            d["dias_restantes"] = (prazo - hoje).days
        except Exception:
            d["prazo_pag"] = "—"
            d["prazo_ok"]  = False
            d["dias_restantes"] = 0
        pagamentos.append(d)

    return render_template("cliente/meus_pagamentos.html", pagamentos=pagamentos)


# ── Confirmação ──

@cliente_bp.route("/confirmacao/<int:ag_id>")
@login_required
def confirmacao(ag_id):
    ag  = Agendamento.buscar_por_id(ag_id)
    pag = Pagamento.buscar_por_agendamento(ag_id) if ag else None
    if not ag or ag.cliente_id != session["cliente_id"]:
        return redirect(url_for("cliente.meus_agendamentos"))
    tema    = Tema.buscar_por_id(ag.tema_id)
    entrega = Entrega.buscar_por_agendamento(ag_id)
    return render_template("cliente/confirmacao.html", ag=ag, pag=pag, tema=tema, entrega=entrega)


@cliente_bp.route("/cancelar/<int:ag_id>", methods=["GET", "POST"])
@login_required
def cancelar(ag_id):
    """
    GET  → tela de confirmação de cancelamento com validação de prazo
    POST → efetiva o cancelamento
    """
    from datetime import date, timedelta

    ag = Agendamento.buscar_por_id(ag_id)
    if not ag or ag.cliente_id != session["cliente_id"]:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    if ag.status != StatusAgendamento.PENDENTE:
        flash(f"Este agendamento está {ag.status} e não pode ser cancelado.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    data_evento  = date.fromisoformat(ag.data_evento)
    prazo_limite = data_evento - timedelta(days=2)
    hoje         = date.today()
    prazo_ok     = hoje <= prazo_limite
    dias_restantes = (prazo_limite - hoje).days

    tema    = Tema.buscar_por_id(ag.tema_id)
    pag     = Pagamento.buscar_por_agendamento(ag_id)
    entrega = Entrega.buscar_por_agendamento(ag_id)
    extras  = AgendamentoItemExtra.listar_por_agendamento(ag_id)

    if request.method == "POST":
        motivo = request.form.get("motivo", "").strip()
        try:
            ag.cancelar(motivo)
            flash(f"Agendamento cancelado com sucesso. {'O reembolso será processado pelo administrador.' if pag and pag.status == 'Pago' else ''}", "sucesso")
            return redirect(url_for("cliente.meus_agendamentos"))
        except ValueError as e:
            flash(e.args[0][0], "erro")
            return render_template(
                "cliente/cancelar.html",
                ag=ag, tema=tema, pag=pag, entrega=entrega, extras=extras,
                prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
                prazo_ok=prazo_ok, dias_restantes=dias_restantes,
            )

    return render_template(
        "cliente/cancelar.html",
        ag=ag, tema=tema, pag=pag, entrega=entrega, extras=extras,
        prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
        prazo_ok=prazo_ok, dias_restantes=dias_restantes,
    )


# ── Reagendamento ──

@cliente_bp.route("/reagendar/<int:ag_id>", methods=["GET", "POST"])
@login_required
def reagendar(ag_id):
    """
    GET  → exibe aviso de taxa + datas disponíveis para reagendamento
    POST → confirma o reagendamento após confirmação do aviso
    """
    from datetime import date, timedelta

    ag = Agendamento.buscar_por_id(ag_id)
    if not ag or ag.cliente_id != session["cliente_id"]:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    if ag.status != StatusAgendamento.PENDENTE:
        flash(f"Apenas agendamentos Pendentes podem ser reagendados. Status: {ag.status}.", "erro")
        return redirect(url_for("cliente.meus_agendamentos"))

    # Valida prazo: 1 dia antes do evento atual
    data_evento   = date.fromisoformat(ag.data_evento)
    prazo_limite  = data_evento - timedelta(days=1)
    hoje          = date.today()
    prazo_ok      = hoje <= prazo_limite
    dias_restantes = (prazo_limite - hoje).days

    tema    = Tema.buscar_por_id(ag.tema_id)
    pag     = Pagamento.buscar_por_agendamento(ag_id)
    historico = Reagendamento.listar_por_agendamento(ag_id)
    datas   = Disponibilidade.listar_livres()
    # Exclui a data atual do evento da lista de disponíveis
    datas   = [d for d in datas if d.data != ag.data_evento]

    if request.method == "POST":
        # Passo 1: cliente confirmou o aviso?
        aviso_confirmado = request.form.get("aviso_confirmado") == "1"
        nova_data        = request.form.get("nova_data", "").strip()

        if not aviso_confirmado:
            flash("Confirme o aviso sobre a taxa de reagendamento.", "erro")
            return render_template(
                "cliente/reagendar.html",
                ag=ag, tema=tema, pag=pag, historico=historico, datas=datas,
                prazo_ok=prazo_ok, prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
                dias_restantes=dias_restantes,
                taxa=TAXA_REAGENDAMENTO,
            )

        if not nova_data:
            flash("Selecione a nova data para o evento.", "erro")
            return render_template(
                "cliente/reagendar.html",
                ag=ag, tema=tema, pag=pag, historico=historico, datas=datas,
                prazo_ok=prazo_ok, prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
                dias_restantes=dias_restantes,
                taxa=TAXA_REAGENDAMENTO,
            )

        try:
            reg = ag.reagendar(nova_data)
            disp_nova = Disponibilidade.buscar_por_data(nova_data)
            data_nova_br = disp_nova.data_br if disp_nova else nova_data.replace("-", "/")
            flash(
                f"Reagendamento confirmado! Nova data: {data_nova_br}. "
                f"Taxa de R$ {TAXA_REAGENDAMENTO:.2f} aplicada. "
                f"Valor total atualizado: R$ {ag.valor_total:.2f}.",
                "sucesso"
            )
            return redirect(url_for("cliente.reagendar_confirmacao", ag_id=ag_id))
        except ValueError as e:
            flash(e.args[0][0], "erro")
            return render_template(
                "cliente/reagendar.html",
                ag=ag, tema=tema, pag=pag, historico=historico, datas=datas,
                prazo_ok=prazo_ok, prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
                dias_restantes=dias_restantes,
                taxa=TAXA_REAGENDAMENTO,
            )

    return render_template(
        "cliente/reagendar.html",
        ag=ag, tema=tema, pag=pag, historico=historico, datas=datas,
        prazo_ok=prazo_ok, prazo_limite=prazo_limite.strftime("%d/%m/%Y"),
        dias_restantes=dias_restantes,
        taxa=TAXA_REAGENDAMENTO,
    )


@cliente_bp.route("/reagendar/<int:ag_id>/confirmacao")
@login_required
def reagendar_confirmacao(ag_id):
    """Tela de confirmação após reagendamento bem-sucedido."""
    ag      = Agendamento.buscar_por_id(ag_id)
    if not ag or ag.cliente_id != session["cliente_id"]:
        return redirect(url_for("cliente.meus_agendamentos"))
    tema    = Tema.buscar_por_id(ag.tema_id)
    pag     = Pagamento.buscar_por_agendamento(ag_id)
    entrega = Entrega.buscar_por_agendamento(ag_id)
    historico = Reagendamento.listar_por_agendamento(ag_id)
    ultimo  = historico[0] if historico else None
    return render_template(
        "cliente/reagendar_confirmacao.html",
        ag=ag, tema=tema, pag=pag, entrega=entrega,
        historico=historico, ultimo=ultimo,
        taxa=TAXA_REAGENDAMENTO,
    )


# ── API: itens de um tema (para seleção de extras) ──

@cliente_bp.route("/api/tema/<int:tema_id>/itens")
@login_required
def api_tema_itens(tema_id):
    """Retorna JSON com os itens de um tema para o seletor de extras."""
    from flask import jsonify
    t = Tema.buscar_por_id(tema_id)
    if not t or not t.ativo:
        return jsonify([])
    itens = t.carregar_itens()
    return jsonify([i.to_dict() for i in itens])


# ── Meus dados ──

@cliente_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    cli = _cliente_atual()
    if request.method == "POST":
        cli.nome     = request.form.get("nome", cli.nome).strip()
        cli.cep      = request.form.get("cep", cli.cep).strip()
        cli.telefone = request.form.get("telefone") or None
        cli.endereco = request.form.get("endereco") or None
        try:
            cli.salvar()
            session["cliente_nome"] = cli.nome
            nova_senha = request.form.get("nova_senha", "").strip()
            if nova_senha:
                cli.atualizar_senha(nova_senha)
            flash("Dados atualizados! ✅", "sucesso")
        except ValueError as e:
            for msg in e.args[0]:
                flash(msg, "erro")
    return render_template("cliente/perfil.html", cliente=cli)


# ═══════════════════════════════════════════════════════════
#  ADMIN BLUEPRINT
# ═══════════════════════════════════════════════════════════

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        u = request.form.get("usuario", "")
        p = request.form.get("senha", "")
        if u == ADMIN_USER and p == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin.dashboard"))
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


# ── Dashboard ──

@admin_bp.route("/")
@admin_required
def dashboard():
    from database import Database
    conn = Database.connect()
    hoje = __import__("datetime").date.today().isoformat()

    stats = {
        "clientes":     conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
        "agendamentos": conn.execute("SELECT COUNT(*) FROM agendamentos").fetchone()[0],
        "pendentes":    conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='Pendente'").fetchone()[0],
        "cancelados":   conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='Cancelado'").fetchone()[0],
        "concluidos":   conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='Concluído'").fetchone()[0],
        "reimb_pend":   conn.execute(
            "SELECT COUNT(*) FROM pagamentos WHERE status='Pendente' AND agendamento_id IN "
            "(SELECT id FROM agendamentos WHERE status='Cancelado')"
        ).fetchone()[0],
    }
    proximas = conn.execute(
        """SELECT a.*, c.nome as cliente_nome FROM agendamentos a
           JOIN clientes c ON c.id=a.cliente_id
           WHERE a.status='Pendente' AND a.data_evento >= ?
           ORDER BY a.data_evento ASC LIMIT 6""", (hoje,)
    ).fetchall()
    datas_ag = conn.execute(
        """SELECT a.data_evento, a.tema_nome, a.status, c.nome as cliente_nome
           FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id
           ORDER BY a.data_evento ASC"""
    ).fetchall()
    conn.close()
    return render_template("admin/dashboard.html", stats=stats, proximas=proximas,
                           datas_ag=datas_ag, hoje=hoje)


# ── Agendamentos ──

@admin_bp.route("/agendamentos")
@admin_required
def agendamentos():
    status = request.args.get("status", "")
    data   = request.args.get("data", "")
    from database import Database
    conn = Database.connect()
    q = """SELECT a.*, c.nome as cliente_nome, c.email, c.telefone,
                  p.status as pag_status, p.valor as pag_valor, p.forma_pagamento
           FROM agendamentos a
           JOIN clientes c ON c.id=a.cliente_id
           LEFT JOIN pagamentos p ON p.agendamento_id=a.id
           WHERE 1=1"""
    params = []
    if status:
        q += " AND a.status=?"; params.append(status)
    if data:
        q += " AND a.data_evento=?"; params.append(data)
    q += " ORDER BY a.data_evento DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return render_template("admin/agendamentos.html", agendamentos=rows,
                           filtro_status=status, filtro_data=data,
                           status_opts=StatusAgendamento.ALL)


@admin_bp.route("/agendamento/<int:ag_id>")
@admin_required
def agendamento_detalhe(ag_id):
    from database import Database
    conn = Database.connect()
    ag = conn.execute(
        """SELECT a.*, c.nome as cli_nome, c.email, c.telefone, c.cpf, c.cep,
                  c.endereco, c.criado_em as cli_criado_em
           FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id
           WHERE a.id=?""", (ag_id,)
    ).fetchone()
    pag = conn.execute(
        """SELECT p.*, r.valor as reemb_valor, r.motivo as reemb_motivo,
                  r.processado_em, fp.nome as fp_nome
           FROM pagamentos p
           LEFT JOIN reembolsos r ON r.pagamento_id=p.id
           LEFT JOIN formas_pagamento fp ON fp.id=r.forma_pagamento_id
           WHERE p.agendamento_id=?""", (ag_id,)
    ).fetchone()
    fps = FormaPagamento.listar_ativas()
    conn.close()
    if not ag:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("admin.agendamentos"))
    return render_template("admin/agendamento_detalhe.html", ag=ag, pag=pag,
                           fps=fps, status_opts=StatusAgendamento.ALL,
                           pag_status_opts=StatusPagamento.ALL)


@admin_bp.route("/agendamento/<int:ag_id>/atualizar", methods=["POST"])
@admin_required
def agendamento_atualizar(ag_id):
    ag = Agendamento.buscar_por_id(ag_id)
    if not ag:
        flash("Não encontrado.", "erro")
        return redirect(url_for("admin.agendamentos"))
    ag.status              = request.form.get("status", ag.status)
    ag.motivo_cancelamento = request.form.get("motivo_cancelamento", ag.motivo_cancelamento)
    ag.valor_total         = float(request.form.get("valor_total", ag.valor_total) or 0)
    ag.entrega_retirada    = request.form.get("entrega_retirada", ag.entrega_retirada)
    ag.salvar()
    # Sincroniza valor do pagamento
    pag = Pagamento.buscar_por_agendamento(ag_id)
    if pag:
        pag.valor = ag.valor_total
        pag.salvar()
    # Libera/ocupa data conforme status
    disp = Disponibilidade.buscar_por_data(ag.data_evento)
    if disp:
        if ag.status == StatusAgendamento.CANCELADO:
            disp.liberar()
        else:
            disp.ocupar()
    flash("Agendamento atualizado! ✅", "sucesso")
    return redirect(url_for("admin.agendamento_detalhe", ag_id=ag_id))


@admin_bp.route("/agendamento/<int:ag_id>/pagamento", methods=["POST"])
@admin_required
def pagamento_atualizar(ag_id):
    """Atualiza status e forma de pagamento (sem reembolso)."""
    pag = Pagamento.buscar_por_agendamento(ag_id)
    if not pag:
        flash("Pagamento não encontrado.", "erro")
        return redirect(url_for("admin.agendamento_detalhe", ag_id=ag_id))

    novo_status = request.form.get("status", pag.status)
    forma       = request.form.get("forma_pagamento", pag.forma_pagamento)

    # Não permite marcar como Reembolsado aqui — use a rota de reembolso dedicada
    if novo_status == StatusPagamento.REEMBOLSADO:
        flash("Para processar reembolso use o botão específico de reembolso.", "erro")
        return redirect(url_for("admin.agendamento_detalhe", ag_id=ag_id))

    pag.status          = novo_status
    pag.forma_pagamento = forma
    pag.salvar()
    flash("Pagamento atualizado! ✅", "sucesso")
    return redirect(url_for("admin.agendamento_detalhe", ag_id=ag_id))


# ── Reembolso ──

@admin_bp.route("/reembolso/<int:ag_id>", methods=["GET", "POST"])
@admin_required
def processar_reembolso(ag_id):
    """
    Fluxo de reembolso conforme caso de uso:
    GET  → exibe dados do pagamento e formulário de reembolso
    POST → processa o reembolso após validações
    """
    from database import Database
    conn = Database.connect()
    ag = conn.execute(
        """SELECT a.*, c.nome as cli_nome, c.email, c.telefone, c.cpf
           FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id
           WHERE a.id=?""", (ag_id,)
    ).fetchone()
    conn.close()

    if not ag:
        flash("Agendamento não encontrado.", "erro")
        return redirect(url_for("admin.agendamentos"))

    pag     = Pagamento.buscar_por_agendamento(ag_id)
    fps     = FormaPagamento.listar_ativas()

    # Passo 7 – Fluxo alternativo: validações antes de exibir
    erros_validacao = []

    if ag["status"] != StatusAgendamento.CANCELADO:
        erros_validacao.append(
            f"O agendamento está com status '{ag['status']}'. "
            f"Reembolso só é permitido para agendamentos Cancelados."
        )
    if not pag:
        erros_validacao.append("Nenhum pagamento encontrado para este agendamento.")
    elif pag.status != StatusPagamento.PAGO:
        erros_validacao.append(
            f"O pagamento está '{pag.status}'. "
            f"Reembolso só é permitido para pagamentos com status 'Pago'."
        )
    elif pag.valor <= 0:
        erros_validacao.append("Valor do pagamento inválido (R$ 0,00). Não é possível processar reembolso.")

    if request.method == "POST":
        if erros_validacao:
            for msg in erros_validacao:
                flash(msg, "erro")
            return redirect(url_for("admin.processar_reembolso", ag_id=ag_id))

        fp_id  = request.form.get("forma_pagamento_id", "").strip()
        motivo = request.form.get("motivo", "").strip()

        # Validações do formulário
        erros_form = []
        if not fp_id:
            erros_form.append("Selecione a forma de devolução do reembolso.")
        if not motivo:
            erros_form.append("Informe o motivo do reembolso.")

        fp = FormaPagamento.buscar_por_id(int(fp_id)) if fp_id else None
        if fp_id and not fp:
            erros_form.append("Forma de pagamento inválida.")

        if erros_form:
            for msg in erros_form:
                flash(msg, "erro")
            return render_template("admin/reembolso.html",
                                   ag=ag, pag=pag, fps=fps,
                                   erros_validacao=[], fp_nome=None)

        # Passos 6, 8, 9, 10: define valor, processa, atualiza status, registra
        try:
            pag.processar_reembolso(
                valor_reembolso = pag.valor,   # passo 6: valor = total pago
                forma_pagamento_id = int(fp_id),
                motivo = motivo,
            )
            # Passo 11: mensagem de confirmação
            flash(
                f"Reembolso de R$ {pag.valor_reembolso:.2f} processado com sucesso "
                f"via {fp.nome} para {ag['cli_nome']}! "
                f"Status atualizado para Reembolsado. ✅",
                "sucesso"
            )
            return redirect(url_for("admin.agendamento_detalhe", ag_id=ag_id))

        except Exception as e:
            flash(f"Erro ao processar reembolso: {str(e)}", "erro")
            return render_template("admin/reembolso.html",
                                   ag=ag, pag=pag, fps=fps,
                                   erros_validacao=[], fp_nome=None)

    return render_template("admin/reembolso.html",
                           ag=ag, pag=pag, fps=fps,
                           erros_validacao=erros_validacao, fp_nome=None)


@admin_bp.route("/reembolsos")
@admin_required
def reembolsos():
    """Lista todos os reembolsos processados e pendentes."""
    from database import Database
    conn = Database.connect()
    # Reembolsos processados
    processados = conn.execute(
        """SELECT r.*, p.valor as pag_valor, p.forma_pagamento,
                  a.id as agendamento_id, a.data_evento, a.tema_nome,
                  c.nome as cli_nome, c.email,
                  fp.nome as fp_nome
           FROM reembolsos r
           JOIN pagamentos p  ON p.id = r.pagamento_id
           JOIN agendamentos a ON a.id = p.agendamento_id
           JOIN clientes c    ON c.id = a.cliente_id
           LEFT JOIN formas_pagamento fp ON fp.id = r.forma_pagamento_id
           ORDER BY r.processado_em DESC"""
    ).fetchall()

    # Agendamentos cancelados com pagamento Pago e sem reembolso (pendentes)
    pendentes = conn.execute(
        """SELECT a.id as ag_id, a.data_evento, a.tema_nome,
                  c.nome as cli_nome, c.email,
                  p.id as pag_id, p.valor as pag_valor, p.forma_pagamento,
                  p.status as pag_status
           FROM agendamentos a
           JOIN clientes c ON c.id=a.cliente_id
           JOIN pagamentos p ON p.agendamento_id=a.id
           LEFT JOIN reembolsos r ON r.pagamento_id=p.id
           WHERE a.status='Cancelado'
             AND p.status='Pago'
             AND r.id IS NULL
           ORDER BY a.data_evento DESC"""
    ).fetchall()
    conn.close()
    return render_template("admin/reembolsos.html",
                           processados=processados, pendentes=pendentes)


# ── Disponibilidades ──

@admin_bp.route("/disponibilidades")
@admin_required
def disponibilidades():
    todas = Disponibilidade.listar_todas()
    return render_template("admin/disponibilidades.html", disponibilidades=todas)


@admin_bp.route("/disponibilidade/<int:disp_id>/toggle", methods=["POST"])
@admin_required
def disponibilidade_toggle(disp_id):
    from database import Database
    conn = Database.connect()
    row  = conn.execute("SELECT * FROM disponibilidades WHERE id=?", (disp_id,)).fetchone()
    conn.close()
    if row:
        disp = Disponibilidade._from_row(row)
        if disp.livre:
            disp.ocupar()
        else:
            disp.liberar()
    return redirect(url_for("admin.disponibilidades"))


@admin_bp.route("/disponibilidade/nova", methods=["POST"])
@admin_required
def disponibilidade_nova():
    """Adiciona nova data disponível. Somente Segunda a Sábado permitidos."""
    from datetime import date as date_cls
    data = request.form.get("data", "").strip()
    if not data:
        flash("Informe uma data.", "erro")
        return redirect(url_for("admin.disponibilidades"))
    try:
        d_obj = date_cls.fromisoformat(data)
        if d_obj.weekday() == 6:  # domingo = 6
            flash("Não é possível cadastrar disponibilidade para Domingo. Cadastre apenas de Segunda a Sábado.", "erro")
            return redirect(url_for("admin.disponibilidades"))
    except ValueError:
        flash("Data inválida.", "erro")
        return redirect(url_for("admin.disponibilidades"))
    conn = __import__("database").Database.connect()
    conn.execute("INSERT OR IGNORE INTO disponibilidades (data, status) VALUES (?, 'Livre')", (data,))
    conn.commit()
    conn.close()
    flash(f"Data {d_obj.strftime('%d/%m/%Y')} adicionada!", "sucesso")
    return redirect(url_for("admin.disponibilidades"))


@admin_bp.route("/disponibilidade/<int:disp_id>/excluir", methods=["POST"])
@admin_required
def disponibilidade_excluir(disp_id):
    conn = __import__("database").Database.connect()
    conn.execute("DELETE FROM disponibilidades WHERE id=? AND status='Livre'", (disp_id,))
    conn.commit()
    conn.close()
    flash("Data removida.", "sucesso")
    return redirect(url_for("admin.disponibilidades"))


# ── Temas ──

@admin_bp.route("/temas")
@admin_required
def temas():
    """Listagem de todos os temas com contagem de itens e imagens."""
    from database import Database
    conn = Database.connect()
    rows = conn.execute(
        """SELECT t.*,
                  COUNT(DISTINCT ti.id) as total_itens,
                  COUNT(DISTINCT img.id) as total_imagens
           FROM temas t
           LEFT JOIN tema_itens  ti  ON ti.tema_id  = t.id
           LEFT JOIN tema_imagens img ON img.tema_id = t.id
           GROUP BY t.id
           ORDER BY t.nome"""
    ).fetchall()
    conn.close()
    return render_template("admin/temas.html", temas=rows)


@admin_bp.route("/temas/novo", methods=["GET", "POST"])
@admin_required
def tema_novo():
    """Formulário de cadastro de novo tema."""
    if request.method == "POST":
        nome      = request.form.get("nome", "").strip()
        descricao = request.form.get("descricao", "").strip()
        valor     = request.form.get("valor", "0").replace(",", ".")
        emoji     = request.form.get("emoji", "🎉").strip() or "🎉"
        cor       = request.form.get("cor", "#a29bfe").strip()

        if not nome:
            flash("Nome é obrigatório.", "erro")
            return render_template("admin/tema_form.html", tema=None, itens=[], imagens=[])

        try:
            valor_f = float(valor)
        except ValueError:
            valor_f = 0.0

        t = Tema(None, nome, descricao, itens_inclusos="", valor=valor_f, emoji=emoji, cor=cor)
        t.salvar()

        # Itens
        nomes_itens = request.form.getlist("item_nome[]")
        qtds        = request.form.getlist("item_qtd[]")
        descs_itens = request.form.getlist("item_desc[]")
        t.sincronizar_itens([
            {"nome": n, "quantidade": q, "descricao": d.strip() or None}
            for n, q, d in zip(nomes_itens, qtds, descs_itens) if n.strip()
        ])

        # Imagens (URLs)
        urls = request.form.getlist("imagem_url[]")
        for i, url in enumerate(urls):
            t.adicionar_imagem(url, ordem=i)

        flash(f"Tema '{t.nome}' cadastrado com sucesso! 🎨", "sucesso")
        return redirect(url_for("admin.tema_detalhe", tid=t.id))

    return render_template("admin/tema_form.html", tema=None, itens=[], imagens=[])


@admin_bp.route("/temas/<int:tid>")
@admin_required
def tema_detalhe(tid):
    """Página de detalhes/edição completa do tema."""
    t = Tema.buscar_por_id(tid)
    if not t:
        flash("Tema não encontrado.", "erro")
        return redirect(url_for("admin.temas"))
    itens   = t.carregar_itens()
    imagens = t.carregar_imagens()
    return render_template("admin/tema_detalhe.html", tema=t, itens=itens, imagens=imagens)


@admin_bp.route("/temas/<int:tid>/editar", methods=["POST"])
@admin_required
def tema_editar(tid):
    """Atualiza dados gerais do tema (nome, descrição, valor, emoji, cor)."""
    t = Tema.buscar_por_id(tid)
    if not t:
        flash("Tema não encontrado.", "erro")
        return redirect(url_for("admin.temas"))

    t.nome      = request.form.get("nome", t.nome).strip() or t.nome
    t.descricao = request.form.get("descricao", t.descricao).strip()
    t.emoji     = request.form.get("emoji", t.emoji).strip() or t.emoji
    t.cor       = request.form.get("cor", t.cor).strip()
    try:
        t.valor = float(request.form.get("valor", t.valor).replace(",","."))
    except (ValueError, AttributeError):
        pass

    t.salvar()
    flash("Dados do tema atualizados! ✅", "sucesso")
    return redirect(url_for("admin.tema_detalhe", tid=tid))


@admin_bp.route("/temas/<int:tid>/itens", methods=["POST"])
@admin_required
def tema_itens_salvar(tid):
    """Substitui todos os itens do tema (sincronização completa)."""
    t = Tema.buscar_por_id(tid)
    if not t:
        flash("Tema não encontrado.", "erro")
        return redirect(url_for("admin.temas"))

    nomes  = request.form.getlist("item_nome[]")
    qtds   = request.form.getlist("item_qtd[]")
    descs  = request.form.getlist("item_desc[]")
    t.sincronizar_itens([
        {"nome": n.strip(), "quantidade": q, "descricao": d.strip() or None}
        for n, q, d in zip(nomes, qtds, descs) if n.strip()
    ])
    flash("Itens do tema atualizados! ✅", "sucesso")
    return redirect(url_for("admin.tema_detalhe", tid=tid))


@admin_bp.route("/temas/<int:tid>/imagens/adicionar", methods=["POST"])
@admin_required
def tema_imagem_adicionar(tid):
    """Adiciona uma URL de imagem ao tema."""
    t   = Tema.buscar_por_id(tid)
    url = request.form.get("url", "").strip()
    if t and url:
        imagens = TemaImagem.listar_por_tema(tid)
        t.adicionar_imagem(url, ordem=len(imagens))
        flash("Imagem adicionada! ✅", "sucesso")
    else:
        flash("Informe uma URL válida.", "erro")
    return redirect(url_for("admin.tema_detalhe", tid=tid))


@admin_bp.route("/temas/<int:tid>/imagens/<int:img_id>/remover", methods=["POST"])
@admin_required
def tema_imagem_remover(tid, img_id):
    """Remove uma imagem do tema."""
    t = Tema.buscar_por_id(tid)
    if t:
        t.remover_imagem(img_id)
        flash("Imagem removida.", "sucesso")
    return redirect(url_for("admin.tema_detalhe", tid=tid))


@admin_bp.route("/temas/<int:tid>/toggle", methods=["POST"])
@admin_required
def tema_toggle(tid):
    """Ativa ou inativa o tema (sem exclusão física)."""
    t = Tema.buscar_por_id(tid)
    if t:
        t.toggle_ativo()
        status = 'ativado' if t.ativo else 'inativado (indisponível no site)'
        flash(f"Tema {status}.", "sucesso")
    return redirect(url_for("admin.tema_detalhe", tid=tid))


# ── Formas de Pagamento ──

@admin_bp.route("/pagamentos")
@admin_required
def pagamentos():
    return render_template("admin/pagamentos.html", fps=FormaPagamento.listar_todas())


@admin_bp.route("/pagamentos/novo", methods=["POST"])
@admin_required
def pagamento_novo():
    try:
        desconto = float(request.form.get("desconto_pct","0").replace(",",".") or 0)
        desconto = max(0.0, min(100.0, desconto))
    except ValueError:
        desconto = 0.0
    fp = FormaPagamento(None,
        request.form.get("nome","").strip(),
        request.form.get("tipo","").strip(),
        request.form.get("descricao","").strip(),
        int(request.form.get("parcelas_max",1) or 1),
        desconto,
    )
    if not fp.nome or not fp.tipo:
        flash("Nome e tipo são obrigatórios.", "erro")
    else:
        fp.salvar()
        flash(f"Forma '{fp.nome}' cadastrada!", "sucesso")
    return redirect(url_for("admin.pagamentos"))


@admin_bp.route("/pagamentos/<int:fp_id>/editar", methods=["POST"])
@admin_required
def pagamento_editar(fp_id):
    """Edita os dados de uma forma de pagamento existente."""
    fp = FormaPagamento.buscar_por_id(fp_id)
    if not fp:
        flash("Forma de pagamento não encontrada.", "erro")
        return redirect(url_for("admin.pagamentos"))
    fp.nome      = request.form.get("nome", fp.nome).strip() or fp.nome
    fp.tipo      = request.form.get("tipo", fp.tipo).strip() or fp.tipo
    fp.descricao = request.form.get("descricao", "").strip()
    try:
        fp.parcelas_max = max(1, int(request.form.get("parcelas_max", fp.parcelas_max) or 1))
    except ValueError:
        pass
    try:
        desconto = float(request.form.get("desconto_pct","0").replace(",",".") or 0)
        fp.desconto_pct = max(0.0, min(100.0, desconto))
    except ValueError:
        pass
    fp.salvar()
    flash(f"Forma '{fp.nome}' atualizada! ✅", "sucesso")
    return redirect(url_for("admin.pagamentos"))


@admin_bp.route("/pagamentos/<int:fp_id>/toggle", methods=["POST"])
@admin_required
def pagamento_toggle(fp_id):
    fp = FormaPagamento.buscar_por_id(fp_id)
    if fp:
        fp.toggle_ativo()
    return redirect(url_for("admin.pagamentos"))


@admin_bp.route("/pagamentos/<int:fp_id>/excluir", methods=["POST"])
@admin_required
def pagamento_excluir(fp_id):
    fp = FormaPagamento.buscar_por_id(fp_id)
    if fp:
        fp.excluir()
        flash("Removido.", "sucesso")
    return redirect(url_for("admin.pagamentos"))


# ── Clientes ──

@admin_bp.route("/clientes")
@admin_required
def clientes():
    busca = request.args.get("q", "").strip()
    todos = Cliente.listar_todos(busca)
    from database import Database
    conn = Database.connect()
    counts = {
        row["cliente_id"]: row["total"]
        for row in conn.execute(
            "SELECT cliente_id, COUNT(*) as total FROM agendamentos GROUP BY cliente_id"
        ).fetchall()
    }
    conn.close()
    return render_template("admin/clientes.html", clientes=todos, counts=counts, busca=busca)


@admin_bp.route("/cliente/<int:cli_id>")
@admin_required
def cliente_detalhe(cli_id):
    cli = Cliente.buscar_por_id(cli_id)
    if not cli:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("admin.clientes"))
    ags = Agendamento.listar_por_cliente(cli_id)
    return render_template("admin/cliente_detalhe.html", cliente=cli, agendamentos=ags)
