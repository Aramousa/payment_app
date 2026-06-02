var clearCodes;

$(document).ready(function() {
    $("#confirmRegenerateTokens").click(function () { confirmRegenerateTokens(); });
    checkTokenLeft();
});

function checkTokenLeft() {
    const get_recovery_token_left = JSON.parse(document.getElementById('get_recovery_token_left').textContent);
    const mfa_redirect = JSON.parse(document.getElementById('mfa_redirect').textContent);
    $.ajax({
        url: get_recovery_token_left, dataType: "JSON",
        success: function (data) {
            var tokenLeft = data.left;
            var html = "";
            if (!!mfa_redirect) {
                html += "<div class='alert alert-success'>✅ ثبت‌نام در روش <strong>" + mfa_redirect +
                    "</strong> موفق بود. لطفاً کدهای بازیابی تولید کنید تا در صورت از دست دادن دسترسی استفاده کنید.</div>";
            }
            if (tokenLeft == 0) {
                html += "<h6 style='color:#dc2626;'>هیچ کد پشتیبانی ندارید. لطفاً کدهای جدید تولید کنید.</h6>";
            } else {
                html += "<p>شما <strong>" + tokenLeft + "</strong> کد پشتیبان دارید.</p>";
            }
            document.getElementById('tokens').innerHTML = html;
        }
    });
}

function confirmRegenerateTokens() {
    var htmlModal = "<h6 style='color:#92400e;'>⚠️ توجه: این کدها فقط یک‌بار قابل مشاهده هستند. " +
        "پس از تولید، آن‌ها را در جای امنی ذخیره کنید.</h6>" +
        "<div class='text-center'><button id='regenerateTokens' class='btn btn-success'>تولید کدهای جدید</button></div>";
    $("#modal-title").html("تولید مجدد کدهای بازیابی");
    $("#modal-body").html(htmlModal);
    $("#regenerateTokens").click(function () { regenerateTokens(); });
    $("#popUpModal").modal('show');
}

function copy() {
    navigator.clipboard.writeText($("#recovery_codes").text());
}

function regenerateTokens() {
    const regen_recovery_tokens = JSON.parse(document.getElementById('regen_recovery_tokens').textContent);
    $.ajax({
        url: regen_recovery_tokens, dataType: "JSON",
        success: function (data) {
            var htmlkey = "<p style='color:#92400e;'>⚠️ این کدها را همین الان ذخیره کنید — دیگر قابل نمایش نخواهند بود.</p>" +
                "<div class='row'><div class='offset-4 col-md-4 bg-white padding-10'>" +
                "<div class='row'><div class='col-6 offset-6'>" +
                "<span id='download_recovery' class='toolbtn' title='دانلود' style='cursor:pointer;'>⬇️</span>&nbsp;&nbsp;" +
                "<span class='toolbtn' id='copy_clipboard' title='کپی' style='cursor:pointer;'>📋</span>" +
                "</div></div><div id='recovery_codes'><pre style='direction:ltr;font-size:14px;'>";
            for (var i = 0; i < data.keys.length; i++) {
                htmlkey += "- " + data.keys[i] + "\n";
            }
            document.getElementById('tokens').innerHTML = htmlkey + "</pre></div></div></div>";
            $("#download_recovery").click(function () { download_recovery(); });
            $("#copy_clipboard").click(function () { copy(); });
            $("#popUpModal").modal('hide');
            clearCodes = data.keys;
        }
    });
}

function download_recovery() {
    var text = clearCodes.join("\n");
    var el = document.createElement('a');
    el.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
    el.setAttribute('download', 'کدهای-بازیابی.txt');
    el.hidden = true;
    document.body.appendChild(el);
    el.click();
    document.body.removeChild(el);
}
