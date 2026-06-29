"""
database.py — Gerenciamento de conexão e inicialização do banco de dados SQLite.
"""
import sqlite3


class Database:
    _path: str = "festas.db"

    @classmethod
    def set_path(cls, path: str) -> None:
        cls._path = path

    @classmethod
    def connect(cls) -> sqlite3.Connection:
        conn = sqlite3.connect(cls._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @classmethod
    def init(cls) -> None:
        conn = cls.connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nome        TEXT    NOT NULL,
                email       TEXT    NOT NULL UNIQUE,
                cpf         TEXT    NOT NULL UNIQUE,
                cep         TEXT    NOT NULL,
                senha_hash  TEXT    NOT NULL,
                telefone    TEXT,
                endereco    TEXT,
                criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS temas (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                nome           TEXT    NOT NULL,
                descricao      TEXT,
                itens_inclusos TEXT,
                valor          REAL    DEFAULT 0.0,
                emoji          TEXT    DEFAULT '🎉',
                cor            TEXT    DEFAULT '#a29bfe',
                imagens        TEXT    DEFAULT '',
                ativo          INTEGER DEFAULT 1,
                criado_em      DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tema_itens (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tema_id    INTEGER NOT NULL,
                nome       TEXT    NOT NULL,
                quantidade INTEGER NOT NULL DEFAULT 1,
                descricao  TEXT,
                FOREIGN KEY (tema_id) REFERENCES temas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tema_imagens (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                tema_id  INTEGER NOT NULL,
                url      TEXT    NOT NULL,
                ordem    INTEGER DEFAULT 0,
                FOREIGN KEY (tema_id) REFERENCES temas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS disponibilidades (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                data   DATE    NOT NULL UNIQUE,
                status TEXT    NOT NULL DEFAULT 'Livre'
            );

            CREATE TABLE IF NOT EXISTS agendamentos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id          INTEGER NOT NULL,
                tema_id             INTEGER NOT NULL,
                tema_nome           TEXT    NOT NULL,
                data_evento         DATE    NOT NULL,
                valor_total         REAL    NOT NULL DEFAULT 0.0,
                status              TEXT    NOT NULL DEFAULT 'Pendente',
                entrega_retirada    TEXT    NOT NULL DEFAULT 'Retirada',
                motivo_cancelamento TEXT,
                observacoes         TEXT,
                criado_em           DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                FOREIGN KEY (tema_id)    REFERENCES temas(id)
            );

            CREATE TABLE IF NOT EXISTS pagamentos (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id    INTEGER NOT NULL UNIQUE,
                valor             REAL    NOT NULL DEFAULT 0.0,
                status            TEXT    NOT NULL DEFAULT 'Pendente',
                forma_pagamento   TEXT,
                valor_reembolso   REAL    DEFAULT 0.0,
                criado_em         DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
            );

            CREATE TABLE IF NOT EXISTS formas_pagamento (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                nome              TEXT    NOT NULL,
                tipo              TEXT    NOT NULL,
                descricao         TEXT,
                parcelas_max      INTEGER DEFAULT 1,
                desconto_pct      REAL    DEFAULT 0.0,
                ativo             INTEGER DEFAULT 1,
                criado_em         DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reagendamentos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id  INTEGER NOT NULL,
                data_anterior   DATE    NOT NULL,
                nova_data       DATE    NOT NULL,
                taxa            REAL    NOT NULL DEFAULT 2.30,
                reagendado_em   DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
            );

            CREATE TABLE IF NOT EXISTS agendamento_itens_extras (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id INTEGER NOT NULL,
                tema_id        INTEGER NOT NULL,
                tema_nome      TEXT    NOT NULL,
                item_nome      TEXT    NOT NULL,
                quantidade     INTEGER NOT NULL DEFAULT 1,
                preco_unitario REAL    NOT NULL DEFAULT 3.50,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id),
                FOREIGN KEY (tema_id)        REFERENCES temas(id)
            );

            CREATE TABLE IF NOT EXISTS entregas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id INTEGER NOT NULL UNIQUE,
                horario      TEXT    NOT NULL,
                endereco     TEXT    NOT NULL,
                observacao   TEXT,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
            );

            CREATE TABLE IF NOT EXISTS reembolsos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                pagamento_id        INTEGER NOT NULL,
                forma_pagamento_id  INTEGER,
                valor               REAL    NOT NULL DEFAULT 0.0,
                motivo              TEXT,
                processado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pagamento_id)       REFERENCES pagamentos(id),
                FOREIGN KEY (forma_pagamento_id) REFERENCES formas_pagamento(id)
            );
        """)
        cls._seed_temas(conn)
        cls._seed_formas_pagamento(conn)
        cls._seed_disponibilidades(conn)
        conn.commit()
        conn.close()

    @classmethod
    def _seed_temas(cls, conn):
        if conn.execute("SELECT COUNT(*) FROM temas").fetchone()[0] == 0:
            temas = [
                (
                    "Jardim Encantado",
                    "Decoração completa com flores artificiais e arranjos naturais que transformam o ambiente em um jardim mágico e encantador.",
                    "Mesas decoradas, arranjos de flores, toalhas florais, painéis de flores, balões temáticos, centro de mesa floral, faixa decorativa",
                    1200.0, "🌸", "#a8e6cf",
                ),
                (
                    "Fundo do Mar",
                    "Mergulhe em uma festa temática com decoração submarina completa, criando um ambiente de fantasia para os pequenos aventureiros.",
                    "Balões azuis e verdes, painéis de oceano, polvos decorativos, peixes de EVA, toalhas temáticas, mesa do bolo, redes decorativas",
                    980.0, "🐠", "#74b9ff",
                ),
                (
                    "Espaço Sideral",
                    "Uma viagem ao cosmos direto na sua festa! Decoração galáctica com estrelas, planetas e muito brilho para os pequenos astronautas.",
                    "Painéis galácticos, balões dourados e prateados, planetas decorativos, estrelas luminosas, mesa temática, capacetes de papelão",
                    1400.0, "🚀", "#6c5ce7",
                ),
                (
                    "Safari Selvagem",
                    "A savana africana na sua festa! Animais, tons terrosos e muita diversão para os pequenos exploradores da natureza.",
                    "Animais de pelúcia decorativos, toalhas estampadas, balões safari, painel de selva, centro de mesa com animais, chapéu de explorador",
                    1100.0, "🦁", "#fdcb6e",
                ),
                (
                    "Princesas e Castelos",
                    "Uma festa digna de realeza! Decoração encantada com coroas, rosas e muito rosa e dourado para as pequenas princesas.",
                    "Coroas decorativas, arranjos de rosas, painéis de castelo, balões dourados e rosa, tiaras para convidadas, varinha mágica",
                    1350.0, "👸", "#fd79a8",
                ),
                (
                    "Super-Heróis",
                    "Missão: festa incrível! Decoração com os heróis favoritos, muita ação e diversão garantida para os pequenos defensores.",
                    "Painéis de heróis, balões coloridos, capas para convidados, centro de mesa temático, faixas decorativas, máscaras",
                    1050.0, "🦸", "#e17055",
                ),
                (
                    "Circo Mágico",
                    "O circo chegou! Cores vibrantes, malabaristas e palhaços para uma festa cheia de magia e alegria para toda a família.",
                    "Tendas decorativas, balões listrados, painéis de circo, enfeites de palhaço, pipoca decorativa, mesas coloridas, chapéus",
                    900.0, "🎪", "#ff7675",
                ),
                (
                    "Fazendinha",
                    "Uma festa no campo com muitos animaizinhos! Decoração rústica e aconchegante para os pequenos fazendeiros de plantão.",
                    "Cercadinhos decorativos, animais de borracha, bandeirinhas, balões temáticos, chapéus de palha, mesa rústica, miniaturas de trator",
                    850.0, "🐄", "#55efc4",
                ),
                (
                    "Unicórnios",
                    "Magia, arco-íris e muito glitter! A festa dos sonhos com decoração encantada e cores vibrantes para os pequenos sonhadores.",
                    "Painéis de arco-íris, chifres decorativos, balões degradê, confetes coloridos, mesa temática, crina decorativa, glitter party",
                    1250.0, "🦄", "#a29bfe",
                ),
                (
                    "Dinossauros",
                    "RAWR! Uma festa pré-histórica incrível com dinossauros, ovos e muita aventura para os pequenos exploradores do jurássico.",
                    "Dinossauros decorativos, ovos de isopor pintados, palmeiras artificiais, balões verdes, painel jurássico, trilha de pegadas",
                    950.0, "🦕", "#00b894",
                ),
            ]
            conn.executemany(
                "INSERT INTO temas (nome, descricao, itens_inclusos, valor, emoji, cor) VALUES (?,?,?,?,?,?)",
                temas,
            )
            # Seed itens por tema
            for tema_row in temas:
                t = conn.execute('SELECT id FROM temas WHERE nome=?', (tema_row[0],)).fetchone()
                if t and tema_row[2]:
                    for item in tema_row[2].split(','):
                        item = item.strip()
                        if item:
                            conn.execute(
                                'INSERT INTO tema_itens (tema_id, nome, quantidade) VALUES (?,?,?)',
                                (t['id'], item, 1)
                            )

    @classmethod
    def _seed_formas_pagamento(cls, conn):
        if conn.execute("SELECT COUNT(*) FROM formas_pagamento").fetchone()[0] == 0:
            fps = [
                # (nome, tipo, descricao, parcelas_max, desconto_pct)
                ("PIX",               "pix",      "Pagamento instantâneo via PIX — sem taxas",       1,  5.0),
                ("Cartão de Débito",  "debito",   "Cartão de débito — aprovação imediata",           1,  0.0),
                ("Cartão de Crédito", "credito",  "Cartão de crédito — parcelamento disponível",    12,  0.0),
                ("Dinheiro",          "dinheiro", "Pagamento em espécie",                            1,  3.0),
                ("Transferência",     "ted",      "TED ou DOC bancário",                             1,  0.0),
            ]
            conn.executemany(
                "INSERT INTO formas_pagamento (nome, tipo, descricao, parcelas_max, desconto_pct) VALUES (?,?,?,?,?)", fps
            )

    @classmethod
    def _seed_disponibilidades(cls, conn):
        """Gera disponibilidades de Segunda a Sábado nos próximos 90 dias."""
        from datetime import date, timedelta
        hoje = date.today()
        for i in range(1, 91):
            d = hoje + timedelta(days=i)
            if d.weekday() in (0, 1, 2, 3, 4, 5):  # Seg=0 a Sáb=5 (excluindo Dom=6)
                conn.execute(
                    "INSERT OR IGNORE INTO disponibilidades (data, status) VALUES (?, 'Livre')",
                    (d.isoformat(),),
                )
