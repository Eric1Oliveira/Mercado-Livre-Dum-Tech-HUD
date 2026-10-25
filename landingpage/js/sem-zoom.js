/* Sem zoom no celular: as telas ja sao desenhadas para o tamanho dele.
 *
 * Tres camadas, porque cada navegador obedece a uma:
 *   1. <meta name="viewport" ... maximum-scale=1, user-scalable=no> - o Android;
 *   2. CSS `touch-action: manipulation` no html - o toque duplo que aproxima;
 *   3. este arquivo - o Safari do iPhone ignora o pedido do meta desde o iOS 10,
 *      entao a pinca (dois dedos) e barrada aqui.
 *
 * Script comum (nao module) e sem nada escrito dentro do HTML: as paginas
 * proibem script em linha (Content-Security-Policy).
 */
(function () {
  "use strict";

  function parar(evento) {
    evento.preventDefault();
  }

  // o gesto de pinca do Safari (iPhone e iPad)
  document.addEventListener("gesturestart", parar, { passive: false });
  document.addEventListener("gesturechange", parar, { passive: false });

  // dois dedos arrastando: a pinca em quem nao tem os eventos de gesto
  document.addEventListener("touchmove", function (evento) {
    if (evento.touches && evento.touches.length > 1) evento.preventDefault();
  }, { passive: false });
})();
