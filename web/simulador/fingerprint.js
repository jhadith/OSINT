/* Fingerprint de dispositivo para el simulador de citas (S8/T21).
 *
 * Espejo local de motor/motor/simulador/fingerprint.py: mismas señales,
 * misma regla de identidad:
 *   device_id = "DEV-" + sha256(JSON canónico de las señales)[0..16]
 * con claves ordenadas, sin espacios y sin escape de acentos.
 *
 * Todo se calcula en este archivo, sin librerías externas ni peticiones de
 * red: el SHA-256 (FIPS 180-4) va embebido abajo.
 */
(function () {
  "use strict";

  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }

  function hex8(x) { return ("00000000" + x.toString(16)).slice(-8); }

  /* UTF-8 de un string → arreglo de bytes (para hashear texto igual que Python). */
  function utf8(texto) {
    var salida = [];
    for (var i = 0; i < texto.length; i++) {
      var cp = texto.charCodeAt(i);
      if (cp >= 0xd800 && cp <= 0xdbff && i + 1 < texto.length) {
        cp = 0x10000 + ((cp - 0xd800) << 10) + (texto.charCodeAt(++i) - 0xdc00);
      }
      if (cp < 0x80) {
        salida.push(cp);
      } else if (cp < 0x800) {
        salida.push(0xc0 | (cp >> 6), 0x80 | (cp & 0x3f));
      } else if (cp < 0x10000) {
        salida.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
      } else {
        salida.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3f),
                   0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
      }
    }
    return salida;
  }

  /* bytes: arreglo de enteros sin signo 0..255 → hex de 64 caracteres. */
  function sha256(bytes) {
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
             0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var l = bytes.length;
    var total = Math.ceil((l + 9) / 64) * 64;
    var m = new Array(total);
    var i;
    for (i = 0; i < total; i++) { m[i] = 0; }
    for (i = 0; i < l; i++) { m[i] = bytes[i]; }
    m[l] = 0x80;
    var bitsHi = Math.floor(l / 0x20000000);
    var bitsLo = (l * 8) >>> 0;
    m[total - 8] = (bitsHi >>> 24) & 0xff;
    m[total - 7] = (bitsHi >>> 16) & 0xff;
    m[total - 6] = (bitsHi >>> 8) & 0xff;
    m[total - 5] = bitsHi & 0xff;
    m[total - 4] = (bitsLo >>> 24) & 0xff;
    m[total - 3] = (bitsLo >>> 16) & 0xff;
    m[total - 2] = (bitsLo >>> 8) & 0xff;
    m[total - 1] = bitsLo & 0xff;

    var w = new Array(64);
    for (var bloque = 0; bloque < total; bloque += 64) {
      for (i = 0; i < 16; i++) {
        w[i] = ((m[bloque + i * 4] << 24) | (m[bloque + i * 4 + 1] << 16) |
                (m[bloque + i * 4 + 2] << 8) | m[bloque + i * 4 + 3]) >>> 0;
      }
      for (i = 16; i < 64; i++) {
        var s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        var s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3],
          e = H[4], f = H[5], g = H[6], h = H[7];
      for (i = 0; i < 64; i++) {
        var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
        var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0;
        d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0;
      H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0;
      H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    return H.map(hex8).join("");
  }

  /* JSON canónico: claves ordenadas, sin espacios, sin escape de acentos.
   * JSON.stringify(obj, clavesOrdenadas) emite solo esas claves en ese orden. */
  function canonica(senales) {
    return JSON.stringify(senales, Object.keys(senales).sort());
  }

  function deviceId(senales) {
    return "DEV-" + sha256(utf8(canonica(senales))).slice(0, 16);
  }

  function senalesDispositivo() {
    var canvas = document.createElement("canvas");
    canvas.width = 200;
    canvas.height = 40;
    var ctx = canvas.getContext("2d");
    ctx.textBaseline = "top";
    ctx.font = "16px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(0, 0, 200, 40);
    ctx.fillStyle = "#069";
    ctx.fillText("Sentinel simulador", 3, 3);
    var huellaCanvas = sha256(utf8(canvas.toDataURL().split(",")[1]));

    var webgl = "";
    var gl = document.createElement("canvas").getContext("webgl");
    if (gl) {
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      if (dbg) { webgl = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)); }
    }

    return {
      canvas: huellaCanvas,
      devicePixelRatio: window.devicePixelRatio || 1,
      screen: screen.width + "x" + screen.height + "x" + screen.colorDepth,
      timezone: -new Date().getTimezoneOffset(),
      userAgent: navigator.userAgent,
      webgl: webgl
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    var senales = senalesDispositivo();
    var id = deviceId(senales);
    document.getElementById("device_id").textContent = id;
    document.getElementById("campo_device").value = id;
    document.getElementById("senales").textContent =
      JSON.stringify(senales, Object.keys(senales).sort(), 2);

    document.getElementById("formulario").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var cuerpo = {
        id_cita: "CIT-SIM-DEMO-" + Date.now(),
        accion: document.getElementById("accion").value,
        canal: "web",
        referencia_paciente: "PAC-SIM-DEMO",
        device_id: id,
        senal_tecnica: ""
      };
      var salida = document.getElementById("resultado");
      fetch("/reservar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo)
      }).then(function (resp) {
        return resp.json().then(function (datos) {
          salida.textContent = "HTTP " + resp.status + "\n" + JSON.stringify(datos, null, 2);
        });
      }).catch(function (err) {
        salida.textContent = "No se pudo enviar (¿está sirviendo el simulador?): " + err;
      });
    });
  });
})();
