$(document).ready(function () {
    document.querySelector("form").addEventListener("submit", function (e) {
        if (!document.getElementById("agree").checked) {
            e.preventDefault();
            alert("لطفاً ابتدا تأییدیه را علامت بزنید.");
        }
    });
});

function checkTrusted() {
    const td_checkTrusted = JSON.parse(document.getElementById('td_checkTrusted').textContent);
    const td_securedevice = JSON.parse(document.getElementById('td_securedevice').textContent);
    $.ajax({
        url: td_checkTrusted,
        success: function (data) {
            if (data == "OK") {
                window.location.href = td_securedevice;
            } else {
                setTimeout('checkTrusted()', 2000);
            }
        }
    });
}

$(document).ready(function () { checkTrusted(); });
