$(document).ready(function() {
    $("#showKey").click(function () { showKey(); });
    $("#showTOTP").click(function () { showTOTP(); });
    $("#verify").click(function () { verify(); });
    addToken();
});

var key = "";

function addToken() {
    const get_new_otop = JSON.parse(document.getElementById('get_new_otop').textContent);
    $.ajax({
        url: get_new_otop, dataType: "JSON",
        success: function (data) {
            window.key = data.secret_key;
            new QRious({ element: document.getElementById('qr'), value: data.qr, size: 280 });
            $("#second_step").show();
        }
    });
}

function showKey() {
    const htmlkey = `<div class="row">
        <div class="col-11"><pre id="totp_secret" style="font-size:18px;letter-spacing:3px;direction:ltr;">` + window.key + `</pre></div>
        <div class="col-1"><span id="copy_clipboard" class="fa fa-clipboard toolbtn" title="کپی" style="cursor:pointer;font-size:18px;">📋</span></div>
    </div>`;
    $("#modal-title").html("کلید مخفی TOTP");
    $("#modal-body").html(htmlkey);
    $("#copy_clipboard").click(function () { navigator.clipboard.writeText($("#totp_secret").text()); });
    $("#popUpModal").modal('show');
}

function verify() {
    const verify_otop        = JSON.parse(document.getElementById('verify_otop').textContent);
    const redirect_html      = JSON.parse(document.getElementById('redirect_html').textContent);
    const reg_success_msg    = JSON.parse(document.getElementById('reg_success_msg').textContent);
    const manage_recovery_codes = JSON.parse(document.getElementById('manage_recovery_codes').textContent);
    const RECOVERY_METHOD    = JSON.parse(document.getElementById('RECOVERY_METHOD').textContent);
    const mfa_home           = JSON.parse(document.getElementById('mfa_home').textContent);
    const answer = $("#answer").val();
    $.ajax({
        url: verify_otop + "?key=" + window.key + "&answer=" + answer,
        success: function (data) {
            if (data == 'Success') {
                $("#res").html("<div class='alert alert-success'>✅ احراز هویت با موفقیت ثبت شد. " +
                    "<a href='" + redirect_html + "'>" + reg_success_msg + "</a></div>");
            } else if (data == "RECOVERY") {
                setTimeout(function () { location.href = manage_recovery_codes; }, 2500);
                $("#res").html("<div class='alert alert-success'>✅ ثبت شد، در حال انتقال به " +
                    "<a href='" + manage_recovery_codes + "'>" + RECOVERY_METHOD + "</a>...</div>");
            } else {
                $("#res").html("<div class='alert alert-danger'>کد وارد شده با کلید مطابقت ندارد. " +
                    "لطفاً دوباره امتحان کنید یا <a href='" + mfa_home + "'>به صفحه اصلی برگردید</a>.</div>");
            }
        }
    });
}

function showTOTP() {
    $("#modal-title").html("اپلیکیشن‌های احراز هویت");
    const html = "<ul style='text-align:right;padding-right:20px;font-size:13px;line-height:2;'>" +
        "<li>اندروید: <a href='https://play.google.com/store/apps/details?id=com.google.android.apps.authenticator2' target='_blank'>Google Authenticator</a> | " +
        "<a href='https://play.google.com/store/apps/details?id=com.authy.authy' target='_blank'>Authy</a></li>" +
        "<li>iPhone/iPad: <a href='https://itunes.apple.com/us/app/authy/id494168017' target='_blank'>Authy</a></li>" +
        "<li>Chrome: <a href='https://chrome.google.com/webstore/detail/authenticator/bhghoamapcdpbohphigoooaddinpkbai' target='_blank'>Google Authenticator</a></li>" +
        "</ul>";
    $("#modal-body").html(html);
    $('#popUpModal').modal('show');
}
