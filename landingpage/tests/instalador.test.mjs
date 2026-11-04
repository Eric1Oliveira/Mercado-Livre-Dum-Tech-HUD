// O botao de baixar segue a versao lancada, sem nunca sair da pasta de downloads.
import assert from "node:assert/strict";
import test from "node:test";

globalThis.location = { search: "" };
const { apontarInstalador, arquivoDaVersao } = await import("../js/instalador.js");

test("aceita o instalador de uma versao", () => {
  assert.equal(arquivoDaVersao("https://dumtechsolution.com/baixar/DumTech-Hub-Setup-1.10.0.exe"),
               "DumTech-Hub-Setup-1.10.0.exe");
});

test("recusa o que nao e instalador nosso", () => {
  for (const url of ["", null, undefined, "https://dumtechsolution.com/baixar/",
                     "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe",
                     "https://dumtechsolution.com/baixar/virus.exe",
                     "http://dumtechsolution.com/baixar/DumTech-Hub-Setup-1.10.0.exe",
                     "https://dumtechsolution.com/baixar/DumTech-Hub-Setup-1.10.0.exe/../x.exe"]) {
    assert.equal(arquivoDaVersao(url), "", String(url));
  }
});

const servidor = (resposta) => {
  globalThis.fetch = async () => {
    if (resposta instanceof Error) throw resposta;
    return { json: async () => resposta };
  };
};

test("aponta os links para a versao no ar, sem sair da pasta", async () => {
  servidor({ ok: true, url: "https://dumtechsolution.com/baixar/DumTech-Hub-Setup-1.10.0.exe" });
  const links = [{ href: "antes" }, { href: "antes" }];
  await apontarInstalador(links, "../baixar/");
  assert.deepEqual(links.map((l) => l.href), Array(2).fill("../baixar/DumTech-Hub-Setup-1.10.0.exe"));
});

test("sem resposta boa, o link generico continua", async () => {
  for (const resposta of [new Error("sem rede"), { ok: false, erro: "muitas_tentativas" },
                          { url: "https://golpe.example/DumTech-Hub-Setup-1.10.0.exe" }]) {
    servidor(resposta);
    const link = { href: "DumTech-Hub-Setup.exe" };
    await apontarInstalador([link]);
    assert.equal(link.href, "DumTech-Hub-Setup.exe");
  }
});
