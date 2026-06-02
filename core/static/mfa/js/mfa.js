$(document).ready(function () {
    const mfa_keys = document.getElementsByClassName('mfa_key');
    for (let i = 0; i < mfa_keys.length; i++) {
        let mfa_key = mfa_keys[i];
        let key_id = mfa_key.dataset.keyId;
        let key_type = mfa_key.dataset.keyType;
        mfa_key.querySelector(`#toggle_${key_id}`).parentElement.addEventListener('click', function () {
            toggleKey(key_id);
        });
        mfa_key.querySelector(`#delete_${key_id}`).addEventListener('click', function () {
            deleteKey(key_id, String(key_type));
        });
    }
});

function confirmDel(id) {
    const mfa_delKey = JSON.parse(document.getElementById('mfa_delKey').textContent);
    const csrf_token = JSON.parse(document.getElementById('csrf_token').textContent);
    $.ajax({
        url: mfa_delKey,
        method: "POST",
        data: {"id": id, "csrfmiddlewaretoken": csrf_token},
        success: function (data) {
            var msg = String(data);
            var fa = msg === 'Deleted' || msg.toLowerCase().includes('deleted') ? 'روش با موفقیت حذف شد.' :
                     msg === 'Error'   || msg.toLowerCase().includes('error')   ? 'خطا در حذف. لطفاً دوباره امتحان کنید.' : msg;
            $("#popUpModal").modal('hide');
            setTimeout(function () { alert(fa); window.location.reload(); }, 300);
        }
    });
}

function deleteKey(id, name) {
    $("#modal-title").html("تأیید حذف");
    $("#modal-body").html(
        "آیا مطمئن هستید که می‌خواهید <strong>«" + name + "»</strong> را حذف کنید؟<br><br>" +
        "<span style='color:#dc2626;font-size:13px;'>⚠️ اگر این تنها روش احراز هویت دو مرحله‌ای شماست، " +
        "ممکن است دسترسی به سامانه را از دست بدهید.</span>"
    );
    $("#actionBtn").remove();
    $("#modal-footer").prepend("<button id='actionBtn' class='btn btn-danger'>حذف</button>");
    $("#actionBtn").click(function () { confirmDel(id); });
    $("#popUpModal").modal('show');
}

function toggleKey(id) {
    const toggle_key = JSON.parse(document.getElementById('toggle_key').textContent);
    $.ajax({
        url: toggle_key + "?id=" + id,
        success: function (data) { if (data == "Error") $("#toggle_" + id).toggle(); },
        error: function () { $("#toggle_" + id).toggle(); }
    });
}
