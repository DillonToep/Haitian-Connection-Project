const form = document.getElementById("login-form");
    const button = document.getElementById("submit-button");
    const message = document.getElementById("message");

    form.addEventListener("submit", async event => {
        event.preventDefault();
        message.textContent = "";
        button.disabled = true;
        button.textContent = "正在登录……";

        try {
            const response = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: form.username.value.trim(),
                    password: form.password.value
                })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "登录失败");
            window.location.replace("/");
        } catch (error) {
            message.textContent = error.message;
            button.disabled = false;
            button.textContent = "登录系统";
        }
    });

