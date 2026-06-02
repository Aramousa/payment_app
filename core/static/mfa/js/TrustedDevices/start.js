$(document).ready(function () {
    const url = JSON.parse(document.getElementById('url').textContent);
    const request_user_username = JSON.parse(document.getElementById('request_user_username').textContent);
    const key = JSON.parse(document.getElementById('key').textContent);
    new QRious({ element: document.getElementById('qr'), value: url + "?u=" + request_user_username + "&k=" + key, size: 200 });
});

function sendEmail() {
    const td_sendemail = JSON.parse(document.getElementById('td_sendemail').textContent);
    $("#modal-title").html("ارسال لینک");
    $("#modal-body").html("در حال ارسال ایمیل، لطفاً صبر کنید...");
    $("#popUpModal").modal('show');
    $.ajax({
        url: td_sendemail,
        success: function (data) {
            var msg = String(data);
            var fa = msg.toLowerCase().includes('sent') || msg.toLowerCase().includes('ok') ?
                     'ایمیل با موفقیت ارسال شد.' : msg;
            alert(fa);
            $("#popUpModal").modal('hide');
        }
    });
}

function failedMFA() {
    $("#modal-body").html(
        "<div class='alert alert-danger'>تأیید هویت ناموفق بود. " +
        "<a href='#' id='getUserAgent'>دوباره امتحان کنید</a></div>"
    );
    $("#getUserAgent").click(function () { getUserAgent(); });
}

function checkMFA() { recheck_mfa(trustDevice, failedMFA, true); }

function trustDevice() {
    const td_trust_device = JSON.parse(document.getElementById('td_trust_device').textContent);
    $.ajax({
        url: td_trust_device,
        success: function (data) {
            if (data == "OK") {
                alert("✅ دستگاه شما ثبت شد. پنجره اصلی تأیید نهایی را نشان می‌دهد.");
                window.location.href = "/mfa/";
            }
        }
    });
}

function getUserAgent() {
    const td_get_useragent = JSON.parse(document.getElementById('td_get_useragent').textContent);
    $.ajax({
        url: td_get_useragent,
        success: function (data) {
            if (data == "")
                setTimeout('getUserAgent()', 5000);
            else {
                $("#modal-title").html("تأیید دستگاه مورد اعتماد");
                $("#actionBtn").remove();
                $("#modal-footer").prepend(
                    "<button id='actionBtn' class='btn btn-success'>تأیید دستگاه</button>"
                );
                $("#actionBtn").click(function () { checkMFA(); });
                $("#modal-body").html(data);
                $("#popUpModal").modal('show');
            }
        }
    });
}

$(document).ready(getUserAgent());
