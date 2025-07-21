let user_id = null;
let interval;
let waktu = 30;

let directLinks = [
  "https://flaredishwater.com/jiq9ypg5i?key=288ddd3f725b2187e03fafc5e0b6268d",
  "https://flaredishwater.com/rzr3yq7eeb?key=0b0ec9a616296fa3520f8f83ff0d9319"
];

// Ambil user_id dari parameter URL
const params = new URLSearchParams(window.location.search);
user_id = params.get("id");

window.addEventListener("DOMContentLoaded", () => {
  const status = document.getElementById("loadingID");
  if (user_id) {
    console.log("? User ID:", user_id);
    if (status) status.innerText = "? Siap diklaim!";
  } else {
    console.warn("? Gagal memuat ID dari URL");
    if (status) status.innerText = "? Gagal memuat ID.";
  }
});

function mulaiTugas() {
  if (!user_id) {
    alert("Gagal memuat ID pengguna. Buka Mini App dari tombol di bot.");
    return;
  }

  if (!directLinks || directLinks.length === 0) {
    alert("Tidak ada iklan tersedia saat ini.");
    return;
  }

  const url = directLinks[Math.floor(Math.random() * directLinks.length)];
  window.location.href = url;

  document.getElementById("klaimStatus").innerHTML = "? Menunggu 30 detik...";
  waktu = 30;
  interval = setInterval(hitunganMundur, 1000);
}

function hitunganMundur() {
  waktu--;
  document.getElementById("klaimStatus").innerHTML = `? Menunggu ${waktu} detik...`;

  if (waktu <= 0) {
    clearInterval(interval);
    klaimPoin();
  }
}

function klaimPoin() {
  document.getElementById("klaimStatus").innerHTML = "?? Mengklaim poin...";

  const reward = Math.floor(Math.random() * (700 - 350 + 1)) + 350;

  fetch("http://159.89.195.47:8000/add_poin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: user_id, amount: reward }),
  })
    .then(res => res.json())
    .then(data => {
      if (data.status === "ok") {
        document.getElementById("klaimStatus").innerHTML = `? Kamu mendapatkan ${reward} poin!`;
      } else {
        document.getElementById("klaimStatus").innerHTML = "? " + data.message;
      }
    })
    .catch(err => {
      console.error("? Gagal klaim:", err);
      document.getElementById("klaimStatus").innerHTML = "? Gagal klaim. Coba lagi.";
    });
}