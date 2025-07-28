export function processPdf() {
    const pdf = document.getElementById("resumePdf");
    if (!pdf) {
        console.error("PDF element not found");
        const tasklogArea = document.getElementById("tasklogArea");
        if (tasklogArea) {
            const msg = "未找到PDF元素，请检查页面内容。";
            const p = document.createElement("p");
            p.textContent = msg;
            tasklogArea.appendChild(p);
        } else {
            alert("未找到PDF元素，请检查页面内容。");
        }
        return;
    }
    // Example: Call backend and output result to tasklogArea
    fetch('/upload/pdf', {
        method: 'POST',
        // 只处理PDF文件上传，不处理论文URL
    })
    .then(response => response.json())
    .then(data => {
        const tasklogArea = document.getElementById("tasklogArea");
        if (tasklogArea) {
            const p = document.createElement("p");
            p.textContent = data.message || "未知响应";
            tasklogArea.appendChild(p);
        }
        // If upload is successful, you may want to call extract API
        if (data.status === "success" && data.file_temp_path) {
            fetch('/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_temp_path: data.file_temp_path })
            })
            .then(response => response.json())
            .then(extractData => {
                const tasklogArea = document.getElementById("tasklogArea");
                if (tasklogArea) {
                    const p = document.createElement("p");
                    p.textContent = extractData.message || "未知响应";
                    tasklogArea.appendChild(p);
                }
            })
            .catch(err => {
                const tasklogArea = document.getElementById("tasklogArea");
                if (tasklogArea) {
                    const p = document.createElement("p");
                    p.textContent = "解析接口调用失败，请重试~";
                    tasklogArea.appendChild(p);
                }
            });
        }
    })
    .catch(err => {
        const tasklogArea = document.getElementById("tasklogArea");
        if (tasklogArea) {
            const p = document.createElement("p");
            p.textContent = "上传接口调用失败，请重试~";
            tasklogArea.appendChild(p);
        }
    });
}