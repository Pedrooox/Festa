"""
models/__init__.py — Modelos de domínio orientados a objetos.

Cada classe encapsula seus dados, validações e operações no banco,
expondo apenas métodos semânticos ao resto da aplicação.
"""
from __future__ import annotations
import hashlib
import re
from datetime import date, datetime
from typing import Optional, List
from database import Database


# ═══════════════════════════════════════════════════════════
#  ENUMS / CONSTANTES
# ═══════════════════════════════════════════════════════════

class StatusAgendamento:
    PENDENTE   = "Pendente"
    CANCELADO  = "Cancelado"
    CONCLUIDO  = "Concluído"
    ALL = [PENDENTE, CANCELADO, CONCLUIDO]

class StatusPagamento:
    PAGO        = "Pago"
    PENDENTE    = "Pendente"
    REEMBOLSADO = "Reembolsado"
    ALL = [PAGO, PENDENTE, REEMBOLSADO]

class StatusDisponibilidade:
    LIVRE   = "Livre"
    OCUPADO = "Ocupado"

class EntregaRetirada:
    ENTREGA  = "Entrega"
    RETIRADA = "Retirada"
    ALL = [ENTREGA, RETIRADA]


# ═══════════════════════════════════════════════════════════
#  CLIENTE
# ═══════════════════════════════════════════════════════════

class Cliente:
    """
    Representa um cliente cadastrado no sistema.

    Campos obrigatórios: nome, email, cpf, cep, senha
    Campos opcionais  : telefone, endereco
    """

    def __init__(
        self,
        id: Optional[int],
        nome: str,
        email: str,
        cpf: str,
        cep: str,
        senha_hash: str,
        telefone: Optional[str] = None,
        endereco: Optional[str] = None,
        criado_em: Optional[str] = None,
    ):
        self.id         = id
        self.nome       = nome
        self.email      = email
        self.cpf        = cpf
        self.cep        = cep
        self.senha_hash = senha_hash
        self.telefone   = telefone
        self.endereco   = endereco
        self.criado_em  = criado_em

    # ── helpers ──────────────────────────────────────

    @staticmethod
    def _hash(senha: str) -> str:
        return hashlib.sha256(senha.encode()).hexdigest()

    @staticmethod
    def _validar_cpf(cpf: str) -> bool:
        """Valida formato e dígitos verificadores do CPF."""
        cpf = re.sub(r"\D", "", cpf)
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False
        for i in range(9, 11):
            soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
            if int(cpf[i]) != (soma * 10 % 11) % 10:
                return False
        return True

    @staticmethod
    def _validar_cep(cep: str) -> bool:
        return bool(re.match(r"^\d{5}-?\d{3}$", cep.strip()))

    @staticmethod
    def _validar_email(email: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))

    def verificar_senha(self, senha: str) -> bool:
        return self.senha_hash == self._hash(senha)

    # ── factory ──────────────────────────────────────

    @classmethod
    def criar(
        cls,
        nome: str,
        email: str,
        cpf: str,
        cep: str,
        senha: str,
        telefone: Optional[str] = None,
        endereco: Optional[str] = None,
    ) -> "Cliente":
        """Valida e cria um novo Cliente (sem persistir)."""
        erros = []

        nome  = nome.strip()
        email = email.strip().lower()
        cpf   = re.sub(r"\D", "", cpf.strip())
        cep   = cep.strip()

        if not nome:
            erros.append("Nome é obrigatório.")
        if not cls._validar_email(email):
            erros.append("E-mail inválido.")
        if not cls._validar_cpf(cpf):
            erros.append("CPF inválido.")
        if not cls._validar_cep(cep):
            erros.append("CEP inválido (formato: 00000-000).")
        if not senha or len(senha) < 6:
            erros.append("Senha deve ter no mínimo 6 caracteres.")

        if erros:
            raise ValueError(erros)

        cpf_fmt = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        return cls(
            id=None,
            nome=nome,
            email=email,
            cpf=cpf_fmt,
            cep=cep,
            senha_hash=cls._hash(senha),
            telefone=telefone.strip() if telefone else None,
            endereco=endereco.strip() if endereco else None,
        )

    # ── persistência ─────────────────────────────────

    def salvar(self) -> "Cliente":
        """INSERT se novo, UPDATE se já existe."""
        conn = Database.connect()
        try:
            if self.id is None:
                # Verifica duplicatas
                if conn.execute("SELECT id FROM clientes WHERE email=?", (self.email,)).fetchone():
                    raise ValueError(["E-mail já cadastrado."])
                if conn.execute("SELECT id FROM clientes WHERE cpf=?", (self.cpf,)).fetchone():
                    raise ValueError(["CPF já cadastrado."])
                cur = conn.execute(
                    "INSERT INTO clientes (nome,email,cpf,cep,senha_hash,telefone,endereco) VALUES (?,?,?,?,?,?,?)",
                    (self.nome, self.email, self.cpf, self.cep,
                     self.senha_hash, self.telefone, self.endereco),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE clientes SET nome=?,email=?,cep=?,telefone=?,endereco=? WHERE id=?",
                    (self.nome, self.email, self.cep,
                     self.telefone, self.endereco, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def atualizar_senha(self, nova_senha: str) -> None:
        if not nova_senha or len(nova_senha) < 6:
            raise ValueError(["Senha deve ter no mínimo 6 caracteres."])
        self.senha_hash = self._hash(nova_senha)
        conn = Database.connect()
        try:
            conn.execute("UPDATE clientes SET senha_hash=? WHERE id=?", (self.senha_hash, self.id))
            conn.commit()
        finally:
            conn.close()

    # ── queries ──────────────────────────────────────

    @classmethod
    def buscar_por_id(cls, cliente_id: int) -> Optional["Cliente"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def buscar_por_email(cls, email: str) -> Optional["Cliente"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM clientes WHERE email=?", (email.lower().strip(),)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def listar_todos(cls, busca: str = "") -> List["Cliente"]:
        conn = Database.connect()
        if busca:
            like = f"%{busca}%"
            rows = conn.execute(
                "SELECT * FROM clientes WHERE nome LIKE ? OR email LIKE ? OR cpf LIKE ? OR telefone LIKE ? ORDER BY nome",
                (like, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row) -> "Cliente":
        d = dict(row)
        return cls(
            id        = d["id"],
            nome      = d["nome"],
            email     = d["email"],
            cpf       = d["cpf"],
            cep       = d["cep"],
            senha_hash= d["senha_hash"],
            telefone  = d.get("telefone"),
            endereco  = d.get("endereco"),
            criado_em = d.get("criado_em"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "email": self.email,
            "cpf": self.cpf, "cep": self.cep, "telefone": self.telefone,
            "endereco": self.endereco, "criado_em": self.criado_em,
        }


# ═══════════════════════════════════════════════════════════
#  ITEM DE TEMA
# ═══════════════════════════════════════════════════════════

class TemaItem:
    """Representa um item incluso em um tema, com nome, quantidade e descrição opcional."""

    def __init__(self, id: Optional[int], tema_id: int, nome: str,
                 quantidade: int = 1, descricao: Optional[str] = None):
        self.id         = id
        self.tema_id    = tema_id
        self.nome       = nome
        self.quantidade = quantidade
        self.descricao  = descricao  # campo opcional

    def salvar(self) -> "TemaItem":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO tema_itens (tema_id, nome, quantidade, descricao) VALUES (?,?,?,?)",
                    (self.tema_id, self.nome, self.quantidade, self.descricao),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE tema_itens SET nome=?, quantidade=?, descricao=? WHERE id=?",
                    (self.nome, self.quantidade, self.descricao, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def excluir(self) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM tema_itens WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def listar_por_tema(cls, tema_id: int) -> List["TemaItem"]:
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM tema_itens WHERE tema_id=? ORDER BY id", (tema_id,)
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def excluir_todos_do_tema(cls, tema_id: int) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM tema_itens WHERE tema_id=?", (tema_id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def _from_row(cls, row) -> "TemaItem":
        d = dict(row)
        return cls(d["id"], d["tema_id"], d["nome"], d.get("quantidade", 1), d.get("descricao"))

    def to_dict(self) -> dict:
        return {"id": self.id, "tema_id": self.tema_id,
                "nome": self.nome, "quantidade": self.quantidade,
                "descricao": self.descricao}


# ═══════════════════════════════════════════════════════════
#  IMAGEM DE TEMA
# ═══════════════════════════════════════════════════════════

class TemaImagem:
    """Representa uma imagem (URL) associada a um tema."""

    def __init__(self, id: Optional[int], tema_id: int, url: str, ordem: int = 0):
        self.id      = id
        self.tema_id = tema_id
        self.url     = url
        self.ordem   = ordem

    def salvar(self) -> "TemaImagem":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO tema_imagens (tema_id, url, ordem) VALUES (?,?,?)",
                    (self.tema_id, self.url, self.ordem),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE tema_imagens SET url=?, ordem=? WHERE id=?",
                    (self.url, self.ordem, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def excluir(self) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM tema_imagens WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def listar_por_tema(cls, tema_id: int) -> List["TemaImagem"]:
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM tema_imagens WHERE tema_id=? ORDER BY ordem, id", (tema_id,)
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def excluir_todas_do_tema(cls, tema_id: int) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM tema_imagens WHERE tema_id=?", (tema_id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def _from_row(cls, row) -> "TemaImagem":
        d = dict(row)
        return cls(d["id"], d["tema_id"], d["url"], d.get("ordem", 0))

    def to_dict(self) -> dict:
        return {"id": self.id, "tema_id": self.tema_id, "url": self.url, "ordem": self.ordem}


# ═══════════════════════════════════════════════════════════
#  TEMA
# ═══════════════════════════════════════════════════════════

class Tema:
    def __init__(self, id: Optional[int], nome: str, descricao: str = "",
                 itens_inclusos: str = "", valor: float = 0.0,
                 emoji: str = "🎉", cor: str = "#a29bfe",
                 imagens: str = "", ativo: bool = True, criado_em: str = ""):
        self.id             = id
        self.nome           = nome
        self.descricao      = descricao
        self.itens_inclusos = itens_inclusos
        self.valor          = valor
        self.emoji          = emoji
        self.cor            = cor
        self.imagens        = imagens
        self.ativo          = ativo
        self.criado_em      = criado_em

    @property
    def itens_lista(self) -> list:
        """Retorna itens_inclusos como lista (split por vírgula)."""
        if not self.itens_inclusos:
            return []
        return [i.strip() for i in self.itens_inclusos.split(',') if i.strip()]

    @property
    def valor_fmt(self) -> str:
        return f"R$ {self.valor:,.2f}".replace(',','X').replace('.',',').replace('X','.')

    @property
    def imagens_lista(self) -> list:
        if not self.imagens:
            return []
        return [i.strip() for i in self.imagens.split(',') if i.strip()]

    def salvar(self) -> "Tema":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO temas (nome,descricao,itens_inclusos,valor,emoji,cor,imagens) VALUES (?,?,?,?,?,?,?)",
                    (self.nome, self.descricao, self.itens_inclusos, self.valor, self.emoji, self.cor, self.imagens),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE temas SET nome=?,descricao=?,itens_inclusos=?,valor=?,emoji=?,cor=?,imagens=? WHERE id=?",
                    (self.nome, self.descricao, self.itens_inclusos, self.valor, self.emoji, self.cor, self.imagens, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def toggle_ativo(self) -> None:
        """Ativa ou inativa o tema. Inativo = indisponível no site."""
        self.ativo = not self.ativo
        conn = Database.connect()
        try:
            conn.execute("UPDATE temas SET ativo=? WHERE id=?", (int(self.ativo), self.id))
            conn.commit()
        finally:
            conn.close()

    def inativar(self) -> None:
        """Inativa o tema sem exclusão física."""
        self.ativo = False
        conn = Database.connect()
        try:
            conn.execute("UPDATE temas SET ativo=0 WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    # ── Itens e Imagens ──────────────────────────────────

    def carregar_itens(self) -> List:
        return TemaItem.listar_por_tema(self.id)

    def carregar_imagens(self) -> List:
        return TemaImagem.listar_por_tema(self.id)

    def sincronizar_itens(self, itens: list) -> None:
        """Substitui todos os itens do tema pela nova lista.
        itens = [{'nome': str, 'quantidade': int, 'descricao': str|None}, ...]
        """
        TemaItem.excluir_todos_do_tema(self.id)
        for it in itens:
            nome      = it.get('nome','').strip()
            qtd       = int(it.get('quantidade', 1) or 1)
            descricao = (it.get('descricao') or '').strip() or None
            if nome:
                TemaItem(None, self.id, nome, qtd, descricao).salvar()

    def adicionar_imagem(self, url: str, ordem: int = 0) -> None:
        if url.strip():
            TemaImagem(None, self.id, url.strip(), ordem).salvar()

    def remover_imagem(self, imagem_id: int) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM tema_imagens WHERE id=? AND tema_id=?", (imagem_id, self.id))
            conn.commit()
        finally:
            conn.close()

    def excluir(self) -> None:
        conn = Database.connect()
        try:
            em_uso = conn.execute(
                "SELECT COUNT(*) FROM agendamentos WHERE tema_id=?", (self.id,)
            ).fetchone()[0]
            if em_uso:
                raise ValueError(["Tema está em uso em agendamentos e não pode ser excluído."])
            conn.execute("DELETE FROM temas WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def buscar_por_id(cls, tema_id: int) -> Optional["Tema"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM temas WHERE id=?", (tema_id,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def listar_ativos(cls) -> List["Tema"]:
        conn = Database.connect()
        rows = conn.execute("SELECT * FROM temas WHERE ativo=1 ORDER BY nome").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def listar_todos(cls) -> List["Tema"]:
        conn = Database.connect()
        rows = conn.execute("SELECT * FROM temas ORDER BY nome").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row) -> "Tema":
        d = dict(row)
        return cls(
            id             = d["id"],
            nome           = d["nome"],
            descricao      = d.get("descricao", ""),
            itens_inclusos = d.get("itens_inclusos", ""),
            valor          = d.get("valor", 0.0),
            emoji          = d.get("emoji", "🎉"),
            cor            = d.get("cor", "#a29bfe"),
            imagens        = d.get("imagens", ""),
            ativo          = bool(d.get("ativo", 1)),
            criado_em      = d.get("criado_em", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "descricao": self.descricao,
            "itens_inclusos": self.itens_inclusos, "valor": self.valor,
            "emoji": self.emoji, "cor": self.cor, "imagens": self.imagens,
            "ativo": self.ativo, "valor_fmt": self.valor_fmt,
            "itens_lista": self.itens_lista,
        }


# ═══════════════════════════════════════════════════════════
#  DISPONIBILIDADE
# ═══════════════════════════════════════════════════════════

class Disponibilidade:
    """
    Representa uma data com seu status (Livre / Ocupado).
    """

    def __init__(self, id: Optional[int], data: str, status: str = StatusDisponibilidade.LIVRE):
        self.id     = id
        self.data   = data   # ISO: YYYY-MM-DD
        self.status = status

    @property
    def livre(self) -> bool:
        return self.status == StatusDisponibilidade.LIVRE

    @property
    def data_br(self) -> str:
        """Formata para dd/mm/aaaa."""
        try:
            d = date.fromisoformat(self.data)
            dias = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
            return f"{d.strftime('%d/%m/%Y')} ({dias[d.weekday()]})"
        except Exception:
            return self.data

    def ocupar(self) -> None:
        self.status = StatusDisponibilidade.OCUPADO
        self._update_status()

    def liberar(self) -> None:
        self.status = StatusDisponibilidade.LIVRE
        self._update_status()

    def _update_status(self) -> None:
        conn = Database.connect()
        try:
            conn.execute("UPDATE disponibilidades SET status=? WHERE id=?", (self.status, self.id))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def buscar_por_data(cls, data: str) -> Optional["Disponibilidade"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM disponibilidades WHERE data=?", (data,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def listar_livres(cls) -> List["Disponibilidade"]:
        hoje = date.today().isoformat()
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM disponibilidades WHERE status='Livre' AND data > ? ORDER BY data LIMIT 30",
            (hoje,),
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def listar_todas(cls) -> List["Disponibilidade"]:
        conn = Database.connect()
        rows = conn.execute("SELECT * FROM disponibilidades ORDER BY data").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row) -> "Disponibilidade":
        d = dict(row)
        return cls(d["id"], d["data"], d["status"])

    def to_dict(self) -> dict:
        return {"id": self.id, "data": self.data, "status": self.status, "data_br": self.data_br}


# ═══════════════════════════════════════════════════════════
#  PAGAMENTO
# ═══════════════════════════════════════════════════════════

class Pagamento:
    """
    Representa o pagamento vinculado a um agendamento.

    Campos: id, agendamento_id, valor, status, forma_pagamento,
            valor_reembolso, criado_em
    """

    def __init__(
        self,
        id: Optional[int],
        agendamento_id: int,
        valor: float = 0.0,
        status: str = StatusPagamento.PENDENTE,
        forma_pagamento: Optional[str] = None,
        valor_reembolso: float = 0.0,
        criado_em: Optional[str] = None,
    ):
        self.id              = id
        self.agendamento_id  = agendamento_id
        self.valor           = valor
        self.status          = status
        self.forma_pagamento = forma_pagamento
        self.valor_reembolso = valor_reembolso
        self.criado_em       = criado_em

    def salvar(self) -> "Pagamento":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO pagamentos (agendamento_id,valor,status,forma_pagamento,valor_reembolso) VALUES (?,?,?,?,?)",
                    (self.agendamento_id, self.valor, self.status, self.forma_pagamento, self.valor_reembolso),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE pagamentos SET valor=?,status=?,forma_pagamento=?,valor_reembolso=? WHERE id=?",
                    (self.valor, self.status, self.forma_pagamento, self.valor_reembolso, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def marcar_pago(self, forma: str) -> None:
        self.status          = StatusPagamento.PAGO
        self.forma_pagamento = forma
        self.salvar()

    def processar_reembolso(self, valor_reembolso: float, forma_pagamento_id: int, motivo: str = "") -> None:
        self.status          = StatusPagamento.REEMBOLSADO
        self.valor_reembolso = valor_reembolso
        self.salvar()
        # Registra na tabela de reembolsos
        conn = Database.connect()
        try:
            conn.execute(
                "INSERT INTO reembolsos (pagamento_id,forma_pagamento_id,valor,motivo) VALUES (?,?,?,?)",
                (self.id, forma_pagamento_id, valor_reembolso, motivo),
            )
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def buscar_por_agendamento(cls, agendamento_id: int) -> Optional["Pagamento"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM pagamentos WHERE agendamento_id=?", (agendamento_id,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row) -> "Pagamento":
        d = dict(row)
        return cls(
            id              = d["id"],
            agendamento_id  = d["agendamento_id"],
            valor           = d.get("valor", 0.0),
            status          = d.get("status", StatusPagamento.PENDENTE),
            forma_pagamento = d.get("forma_pagamento"),
            valor_reembolso = d.get("valor_reembolso", 0.0),
            criado_em       = d.get("criado_em"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agendamento_id": self.agendamento_id,
            "valor": self.valor, "status": self.status,
            "forma_pagamento": self.forma_pagamento,
            "valor_reembolso": self.valor_reembolso,
            "criado_em": self.criado_em,
        }


# ═══════════════════════════════════════════════════════════
#  AGENDAMENTO
# ═══════════════════════════════════════════════════════════

class Agendamento:
    """
    Representa um agendamento de festa.

    Campos: id, cliente_id, tema_id, tema_nome, data_evento, valor_total,
            status, entrega_retirada, motivo_cancelamento, observacoes
    """

    def __init__(
        self,
        id: Optional[int],
        cliente_id: int,
        tema_id: int,
        tema_nome: str,
        data_evento: str,
        valor_total: float = 0.0,
        status: str = StatusAgendamento.PENDENTE,
        entrega_retirada: str = EntregaRetirada.RETIRADA,
        motivo_cancelamento: Optional[str] = None,
        observacoes: Optional[str] = None,
        criado_em: Optional[str] = None,
    ):
        self.id                  = id
        self.cliente_id          = cliente_id
        self.tema_id             = tema_id
        self.tema_nome           = tema_nome
        self.data_evento         = data_evento
        self.valor_total         = valor_total
        self.status              = status
        self.entrega_retirada    = entrega_retirada
        self.motivo_cancelamento = motivo_cancelamento
        self.observacoes         = observacoes
        self.criado_em           = criado_em

    # ── ações de domínio ─────────────────────────────

    def cancelar(self, motivo: str = "") -> None:
        """
        Cancela o agendamento.
        Regra: só é permitido até 2 dias antes da data do evento.
        """
        from datetime import date, timedelta

        if self.status == StatusAgendamento.CANCELADO:
            raise ValueError(["Este agendamento já foi cancelado."])
        if self.status == StatusAgendamento.CONCLUIDO:
            raise ValueError(["Não é possível cancelar um agendamento já concluído."])

        data_evento = date.fromisoformat(self.data_evento)
        prazo_limite = data_evento - timedelta(days=2)
        if date.today() > prazo_limite:
            raise ValueError([
                f"Cancelamento não permitido. O prazo era até "
                f"{prazo_limite.strftime('%d/%m/%Y')} "
                f"(2 dias antes do evento em {data_evento.strftime('%d/%m/%Y')})."
            ])

        if not motivo or not motivo.strip():
            raise ValueError(["Informe o motivo do cancelamento."])

        self.status              = StatusAgendamento.CANCELADO
        self.motivo_cancelamento = motivo.strip()
        self.salvar()

        # Libera a data no calendário
        disp = Disponibilidade.buscar_por_data(self.data_evento)
        if disp:
            disp.liberar()

    def reagendar(self, nova_data: str) -> "Reagendamento":
        """
        Reagenda o evento para uma nova data.
        Regras:
          - Status deve ser Pendente
          - Só permitido com pelo menos 1 dia de antecedência da data atual do evento
          - Nova data deve estar disponível
          - Cobra taxa de R$ 2,30 (adicionada ao valor_total)
          - Libera a data anterior e ocupa a nova data
        """
        from datetime import date, timedelta

        if self.status != StatusAgendamento.PENDENTE:
            raise ValueError([f"Só é possível reagendar agendamentos Pendentes. Status atual: {self.status}."])

        data_atual_evento = date.fromisoformat(self.data_evento)
        prazo_limite      = data_atual_evento - timedelta(days=1)
        hoje              = date.today()

        if hoje > prazo_limite:
            raise ValueError([
                f"Reagendamento não permitido. O prazo era até "
                f"{prazo_limite.strftime('%d/%m/%Y')} "
                f"(1 dia antes do evento em {data_atual_evento.strftime('%d/%m/%Y')})."
            ])

        if nova_data == self.data_evento:
            raise ValueError(["A nova data deve ser diferente da data atual do evento."])

        disp_nova = Disponibilidade.buscar_por_data(nova_data)
        if not disp_nova or disp_nova.status != StatusDisponibilidade.LIVRE:
            raise ValueError(["A data selecionada não está disponível. Escolha outra data."])

        # Salva histórico
        data_anterior = self.data_evento
        reg = Reagendamento(None, self.id, data_anterior, nova_data)
        reg.salvar()

        # Aplica taxa ao valor total
        self.valor_total = round(self.valor_total + TAXA_REAGENDAMENTO, 2)
        self.data_evento = nova_data
        self.salvar()

        # Atualiza pagamento
        pag = Pagamento.buscar_por_agendamento(self.id)
        if pag:
            pag.valor = self.valor_total
            pag.salvar()

        # Libera data anterior e ocupa nova data
        disp_anterior = Disponibilidade.buscar_por_data(data_anterior)
        if disp_anterior:
            disp_anterior.liberar()
        disp_nova.ocupar()

        return reg

    def concluir(self) -> None:
        if self.status != StatusAgendamento.PENDENTE:
            raise ValueError(["Apenas agendamentos Pendentes podem ser concluídos."])
        self.status = StatusAgendamento.CONCLUIDO
        self.salvar()

    # ── persistência ─────────────────────────────────

    def salvar(self) -> "Agendamento":
        is_insert = self.id is None
        conn = Database.connect()
        try:
            if is_insert:
                cur = conn.execute(
                    """INSERT INTO agendamentos
                       (cliente_id,tema_id,tema_nome,data_evento,valor_total,status,
                        entrega_retirada,motivo_cancelamento,observacoes)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (self.cliente_id, self.tema_id, self.tema_nome, self.data_evento,
                     self.valor_total, self.status, self.entrega_retirada,
                     self.motivo_cancelamento, self.observacoes),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE agendamentos SET tema_id=?,tema_nome=?,data_evento=?,valor_total=?,
                       status=?,entrega_retirada=?,motivo_cancelamento=?,observacoes=? WHERE id=?""",
                    (self.tema_id, self.tema_nome, self.data_evento, self.valor_total,
                     self.status, self.entrega_retirada, self.motivo_cancelamento,
                     self.observacoes, self.id),
                )
            conn.commit()
        finally:
            conn.close()
        if is_insert:
            Pagamento(id=None, agendamento_id=self.id, valor=self.valor_total).salvar()
            disp = Disponibilidade.buscar_por_data(self.data_evento)
            if disp:
                disp.ocupar()
        return self

    # ── queries ──────────────────────────────────────

    @classmethod
    def buscar_por_id(cls, ag_id: int) -> Optional["Agendamento"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM agendamentos WHERE id=?", (ag_id,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def listar_por_cliente(cls, cliente_id: int) -> List["Agendamento"]:
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM agendamentos WHERE cliente_id=? ORDER BY data_evento DESC", (cliente_id,)
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def listar_todos(cls, status: str = "", data: str = "") -> List["Agendamento"]:
        conn  = Database.connect()
        query = "SELECT * FROM agendamentos WHERE 1=1"
        params: list = []
        if status:
            query += " AND status=?"; params.append(status)
        if data:
            query += " AND data_evento=?"; params.append(data)
        query += " ORDER BY data_evento DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row) -> "Agendamento":
        d = dict(row)
        return cls(
            id                  = d["id"],
            cliente_id          = d["cliente_id"],
            tema_id             = d["tema_id"],
            tema_nome           = d["tema_nome"],
            data_evento         = d["data_evento"],
            valor_total         = d.get("valor_total", 0.0),
            status              = d.get("status", StatusAgendamento.PENDENTE),
            entrega_retirada    = d.get("entrega_retirada", EntregaRetirada.RETIRADA),
            motivo_cancelamento = d.get("motivo_cancelamento"),
            observacoes         = d.get("observacoes"),
            criado_em           = d.get("criado_em"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "cliente_id": self.cliente_id,
            "tema_id": self.tema_id, "tema_nome": self.tema_nome,
            "data_evento": self.data_evento, "valor_total": self.valor_total,
            "status": self.status, "entrega_retirada": self.entrega_retirada,
            "motivo_cancelamento": self.motivo_cancelamento,
            "observacoes": self.observacoes, "criado_em": self.criado_em,
        }


# ═══════════════════════════════════════════════════════════
#  REAGENDAMENTO
# ═══════════════════════════════════════════════════════════

TAXA_REAGENDAMENTO = 2.30   # R$ cobrados por reagendamento

class Reagendamento:
    """
    Registra o histórico de cada reagendamento realizado.
    Guarda a data anterior, a nova data e a taxa cobrada.
    """

    def __init__(
        self,
        id: Optional[int],
        agendamento_id: int,
        data_anterior: str,
        nova_data: str,
        taxa: float = TAXA_REAGENDAMENTO,
        reagendado_em: Optional[str] = None,
    ):
        self.id             = id
        self.agendamento_id = agendamento_id
        self.data_anterior  = data_anterior
        self.nova_data      = nova_data
        self.taxa           = taxa
        self.reagendado_em  = reagendado_em

    def salvar(self) -> "Reagendamento":
        conn = Database.connect()
        try:
            cur = conn.execute(
                """INSERT INTO reagendamentos
                   (agendamento_id, data_anterior, nova_data, taxa)
                   VALUES (?,?,?,?)""",
                (self.agendamento_id, self.data_anterior, self.nova_data, self.taxa),
            )
            self.id = cur.lastrowid
            conn.commit()
            return self
        finally:
            conn.close()

    @classmethod
    def listar_por_agendamento(cls, agendamento_id: int) -> List["Reagendamento"]:
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM reagendamentos WHERE agendamento_id=? ORDER BY reagendado_em DESC",
            (agendamento_id,),
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def total_taxas_por_agendamento(cls, agendamento_id: int) -> float:
        conn = Database.connect()
        result = conn.execute(
            "SELECT COALESCE(SUM(taxa), 0) FROM reagendamentos WHERE agendamento_id=?",
            (agendamento_id,),
        ).fetchone()[0]
        conn.close()
        return round(float(result), 2)

    @classmethod
    def _from_row(cls, row) -> "Reagendamento":
        d = dict(row)
        return cls(d["id"], d["agendamento_id"], d["data_anterior"],
                   d["nova_data"], d.get("taxa", TAXA_REAGENDAMENTO), d.get("reagendado_em"))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agendamento_id": self.agendamento_id,
            "data_anterior": self.data_anterior, "nova_data": self.nova_data,
            "taxa": self.taxa, "reagendado_em": self.reagendado_em,
        }


# ═══════════════════════════════════════════════════════════
#  ITEM EXTRA DE AGENDAMENTO
# ═══════════════════════════════════════════════════════════

PRECO_ITEM_EXTRA   = 3.50
MAX_QTD_ITEM_EXTRA = 5

class AgendamentoItemExtra:
    """
    Item de outro tema adicionado a um agendamento.
    Preço fixo: R$ 3,50 por unidade.
    Quantidade máxima por item: 5.
    """

    def __init__(
        self,
        id: Optional[int],
        agendamento_id: int,
        tema_id: int,
        tema_nome: str,
        item_nome: str,
        quantidade: int = 1,
        preco_unitario: float = PRECO_ITEM_EXTRA,
    ):
        self.id             = id
        self.agendamento_id = agendamento_id
        self.tema_id        = tema_id
        self.tema_nome      = tema_nome
        self.item_nome      = item_nome
        self.quantidade     = min(int(quantidade), MAX_QTD_ITEM_EXTRA)
        self.preco_unitario = preco_unitario

    @property
    def subtotal(self) -> float:
        return round(self.quantidade * self.preco_unitario, 2)

    def salvar(self) -> "AgendamentoItemExtra":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    """INSERT INTO agendamento_itens_extras
                       (agendamento_id, tema_id, tema_nome, item_nome, quantidade, preco_unitario)
                       VALUES (?,?,?,?,?,?)""",
                    (self.agendamento_id, self.tema_id, self.tema_nome,
                     self.item_nome, self.quantidade, self.preco_unitario),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE agendamento_itens_extras SET quantidade=? WHERE id=?",
                    (self.quantidade, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def excluir(self) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM agendamento_itens_extras WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def listar_por_agendamento(cls, agendamento_id: int) -> List["AgendamentoItemExtra"]:
        conn = Database.connect()
        rows = conn.execute(
            "SELECT * FROM agendamento_itens_extras WHERE agendamento_id=? ORDER BY tema_nome, item_nome",
            (agendamento_id,),
        ).fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def excluir_por_agendamento(cls, agendamento_id: int) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM agendamento_itens_extras WHERE agendamento_id=?", (agendamento_id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def total_por_agendamento(cls, agendamento_id: int) -> float:
        """Retorna o valor total dos itens extras de um agendamento."""
        conn = Database.connect()
        result = conn.execute(
            "SELECT COALESCE(SUM(quantidade * preco_unitario), 0) FROM agendamento_itens_extras WHERE agendamento_id=?",
            (agendamento_id,),
        ).fetchone()[0]
        conn.close()
        return round(result, 2)

    @classmethod
    def _from_row(cls, row) -> "AgendamentoItemExtra":
        d = dict(row)
        return cls(d["id"], d["agendamento_id"], d["tema_id"], d["tema_nome"],
                   d["item_nome"], d.get("quantidade", 1), d.get("preco_unitario", PRECO_ITEM_EXTRA))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agendamento_id": self.agendamento_id,
            "tema_id": self.tema_id, "tema_nome": self.tema_nome,
            "item_nome": self.item_nome, "quantidade": self.quantidade,
            "preco_unitario": self.preco_unitario, "subtotal": self.subtotal,
        }


# ═══════════════════════════════════════════════════════════
#  ENTREGA
# ═══════════════════════════════════════════════════════════

class Entrega:
    """
    Dados de entrega vinculados a um agendamento.
    Obrigatório quando entrega_retirada == 'Entrega'.
    Campos obrigatórios: horario, endereco
    Campo opcional    : observacao
    """

    def __init__(
        self,
        id: Optional[int],
        agendamento_id: int,
        horario: str,
        endereco: str,
        observacao: Optional[str] = None,
    ):
        self.id             = id
        self.agendamento_id = agendamento_id
        self.horario        = horario
        self.endereco       = endereco
        self.observacao     = observacao

    def salvar(self) -> "Entrega":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO entregas (agendamento_id, horario, endereco, observacao) VALUES (?,?,?,?)",
                    (self.agendamento_id, self.horario, self.endereco, self.observacao),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE entregas SET horario=?, endereco=?, observacao=? WHERE id=?",
                    (self.horario, self.endereco, self.observacao, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    @classmethod
    def buscar_por_agendamento(cls, agendamento_id: int) -> Optional["Entrega"]:
        conn = Database.connect()
        row  = conn.execute(
            "SELECT * FROM entregas WHERE agendamento_id=?", (agendamento_id,)
        ).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row) -> "Entrega":
        d = dict(row)
        return cls(d["id"], d["agendamento_id"], d["horario"], d["endereco"], d.get("observacao"))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agendamento_id": self.agendamento_id,
            "horario": self.horario, "endereco": self.endereco,
            "observacao": self.observacao,
        }


# ═══════════════════════════════════════════════════════════
#  FORMA DE PAGAMENTO (auxiliar admin)
# ═══════════════════════════════════════════════════════════

class FormaPagamento:
    def __init__(self, id: Optional[int], nome: str, tipo: str,
                 descricao: str = "", parcelas_max: int = 1,
                 desconto_pct: float = 0.0,
                 ativo: bool = True, criado_em: str = ""):
        self.id           = id
        self.nome         = nome
        self.tipo         = tipo
        self.descricao    = descricao
        self.parcelas_max = parcelas_max
        self.desconto_pct = desconto_pct   # ex: 5.0 = 5% de desconto
        self.ativo        = ativo
        self.criado_em    = criado_em

    @property
    def tem_desconto(self) -> bool:
        return self.desconto_pct > 0

    @property
    def desconto_fmt(self) -> str:
        return f"{self.desconto_pct:.1f}%".replace(".", ",")

    @property
    def tem_parcelas(self) -> bool:
        return self.tipo == "credito" and self.parcelas_max > 1

    def calcular_valor_com_desconto(self, valor: float) -> float:
        """Retorna o valor após aplicar o desconto percentual."""
        if self.desconto_pct <= 0:
            return round(valor, 2)
        return round(valor * (1 - self.desconto_pct / 100), 2)

    def calcular_parcela(self, valor: float, parcelas: int) -> float:
        """Calcula o valor de cada parcela (sem juros)."""
        parcelas = max(1, min(parcelas, self.parcelas_max))
        return round(valor / parcelas, 2)

    def salvar(self) -> "FormaPagamento":
        conn = Database.connect()
        try:
            if self.id is None:
                cur = conn.execute(
                    "INSERT INTO formas_pagamento (nome,tipo,descricao,parcelas_max,desconto_pct) VALUES (?,?,?,?,?)",
                    (self.nome, self.tipo, self.descricao, self.parcelas_max, self.desconto_pct),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE formas_pagamento SET nome=?,tipo=?,descricao=?,parcelas_max=?,desconto_pct=? WHERE id=?",
                    (self.nome, self.tipo, self.descricao, self.parcelas_max, self.desconto_pct, self.id),
                )
            conn.commit()
            return self
        finally:
            conn.close()

    def toggle_ativo(self) -> None:
        self.ativo = not self.ativo
        conn = Database.connect()
        try:
            conn.execute("UPDATE formas_pagamento SET ativo=? WHERE id=?", (int(self.ativo), self.id))
            conn.commit()
        finally:
            conn.close()

    def excluir(self) -> None:
        conn = Database.connect()
        try:
            conn.execute("DELETE FROM formas_pagamento WHERE id=?", (self.id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def listar_ativas(cls) -> List["FormaPagamento"]:
        conn = Database.connect()
        rows = conn.execute("SELECT * FROM formas_pagamento WHERE ativo=1 ORDER BY nome").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def listar_todas(cls) -> List["FormaPagamento"]:
        conn = Database.connect()
        rows = conn.execute("SELECT * FROM formas_pagamento ORDER BY nome").fetchall()
        conn.close()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def buscar_por_id(cls, fp_id: int) -> Optional["FormaPagamento"]:
        conn = Database.connect()
        row  = conn.execute("SELECT * FROM formas_pagamento WHERE id=?", (fp_id,)).fetchone()
        conn.close()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row) -> "FormaPagamento":
        d = dict(row)
        return cls(d["id"], d["nome"], d["tipo"], d.get("descricao",""),
                   d.get("parcelas_max",1), d.get("desconto_pct",0.0),
                   bool(d.get("ativo",1)), d.get("criado_em",""))

    def to_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "tipo": self.tipo,
                "descricao": self.descricao, "parcelas_max": self.parcelas_max,
                "desconto_pct": self.desconto_pct, "ativo": self.ativo}
