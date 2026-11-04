"""O que o Hub diz ao cliente do plano mensal.

Tudo aqui e texto puro, sem tela: a faixa do Inicio, a faixa da janela em modo
consulta e a linha da tela de Licenca leem daqui, e os testes tambem.

Regra de ouro: licenca vitalicia NAO recebe nada desta pagina - nem aviso de
pagamento, nem vencimento, nem modo consulta da mensalidade. Toda funcao
publica comeca perguntando `licenca.mensal`.

Os textos falam com o dono de um pequeno negocio: frases completas, o que muda
para ele e o que fazer, sem termo tecnico e sem susto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from .licensing import License


@dataclass(frozen=True)
class Faixa:
    """Um recado no topo do Inicio."""

    situacao: str   # teste | pendente | consulta
    tom: str        # accent | warning
    titulo: str
    texto: str
    acao: str       # assinar | whatsapp
    botao: str


def _data(dia: date | None) -> str:
    return dia.strftime("%d/%m/%Y") if dia else ""


def faixa(licenca: License, hoje: date | None = None) -> Faixa | None:
    """O recado do plano mensal, ou None (vitalicia, em dia, servidor antigo)."""
    if not licenca.mensal:
        return None
    # o dia como o servidor conta (UTC): e nele que o prazo vence, la e aqui
    hoje = hoje or datetime.now(timezone.utc).date()
    situacao = licenca.situacao_cobranca
    ate = licenca.cobranca_ate
    cancelou = licenca.cobranca_motivo == "cancelou"

    if situacao == "teste":
        restam = max(1, (ate - hoje).days + 1) if ate else None
        if restam is None or restam > 2:
            titulo = f"Seu teste grátis: faltam {restam} dias" if restam else "Você está no teste grátis"
        elif restam == 2:
            titulo = "Seu teste grátis termina amanhã"
        else:
            titulo = "Hoje é o último dia do seu teste grátis"
        return Faixa(
            "teste", "warning" if restam is not None and restam <= 2 else "accent", titulo,
            "Você está usando todos os módulos do DumTech Hub. Para continuar depois do teste, "
            "é só assinar: tudo o que você lançou continua aqui.",
            "assinar", "Assinar")

    if situacao == "pendente" and cancelou:
        return Faixa(
            "pendente", "warning", "Sua assinatura foi encerrada",
            f"Tudo funciona normalmente até {_data(ate)}. Depois disso, o DumTech Hub fica só "
            "para consulta, e os seus dados continuam guardados. Mudou de ideia? É só assinar de novo.",
            "assinar", "Assinar de novo")

    if situacao == "pendente":
        return Faixa(
            "pendente", "warning", "Não conseguimos confirmar a sua mensalidade",
            f"Nada muda por enquanto: tudo funciona normalmente até {_data(ate)}. Se você já pagou, "
            "pode desconsiderar este aviso. Se precisar de ajuda, a DumTech resolve com você pelo WhatsApp.",
            "whatsapp", "Falar com a DumTech")

    if situacao == "consulta":
        if licenca.tipo == "teste":
            return Faixa(
                "consulta", "warning", "Seu teste grátis terminou",
                "Está tudo guardado: você pode abrir os módulos para ver e exportar o que lançou. "
                "Para voltar a lançar, é só assinar.",
                "assinar", "Assinar")
        if cancelou:
            return Faixa(
                "consulta", "warning", "Sua assinatura foi encerrada",
                "Os seus dados continuam guardados: você pode abrir os módulos para ver e exportar "
                "tudo. Quando quiser voltar, é só assinar de novo.",
                "assinar", "Assinar de novo")
        return Faixa(
            "consulta", "warning", "Seu DumTech Hub está só para consulta",
            "Não conseguimos confirmar a sua mensalidade. Os seus dados estão guardados e você pode "
            "ver e exportar tudo. Assim que o pagamento for confirmado, o Hub volta ao normal sozinho.",
            "whatsapp", "Falar com a DumTech")

    return None


def texto_consulta(licenca: License) -> str | None:
    """Por que o modulo abriu so para consulta, quando o motivo e a mensalidade.

    Vai na faixa da janela do modulo e na caixa de quem tenta gravar. Vitalicia
    (ou outro motivo): None, e o Hub usa o texto de sempre.
    """
    if not licenca.mensal or licenca.situacao_cobranca != "consulta":
        return None
    if licenca.tipo == "teste":
        return ("Seu teste grátis terminou. Dá para ver e exportar tudo o que você lançou; "
                "para voltar a lançar, é só assinar.")
    if licenca.cobranca_motivo == "cancelou":
        return ("A sua assinatura foi encerrada. Dá para ver e exportar tudo o que você lançou; "
                "para voltar a lançar, é só assinar de novo.")
    return ("A sua mensalidade está pendente. Dá para ver e exportar tudo; assim que o "
            "pagamento for confirmado, tudo volta ao normal.")


def linha_do_plano(licenca: License, hoje: date | None = None) -> str | None:
    """A linha "Plano" da tela de Licenca. Vitalicia: None (a tela segue como era)."""
    if not licenca.mensal:
        return None
    situacao = licenca.situacao_cobranca
    ate = _data(licenca.cobranca_ate)
    if situacao == "teste":
        return f"Teste grátis até {ate}" if ate else "Teste grátis"
    if situacao == "em_dia":
        return "Plano mensal, em dia"
    if situacao == "pendente":
        if licenca.cobranca_motivo == "cancelou":
            return f"Plano mensal encerrado, funciona até {ate}"
        return f"Plano mensal, pagamento a confirmar até {ate}"
    if situacao == "consulta":
        return "Teste grátis encerrado: só consulta" if licenca.tipo == "teste" \
            else "Plano mensal: só consulta"
    return "Plano mensal"
