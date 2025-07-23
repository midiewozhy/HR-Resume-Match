// 上传简历
document.getElementById('upload-resume-btn').addEventListener('click', async () => {
    const fileInput = document.getElementById('resume-file');
    const file = fileInput.files[0];
    const statusElement = document.getElementById('resume-upload-status');

    if (!file) {
        statusElement.textContent = '请选择一个 PDF 文件';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/resources/upload/pdf', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        statusElement.textContent = data.message;

        if (data.status === 'success') {
            // 提取简历内容
            const extractResponse = await fetch('/api/resources/extract', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ file_temp_path: data.file_temp_path })
            });
            const extractData = await extractResponse.json();
            document.getElementById('resume-upload-status').textContent = extractData.message;
        }
    } catch (error) {
        statusElement.textContent = '上传简历时出现错误';
    }
});

// 上传论文链接
document.getElementById('upload-paper-url-btn').addEventListener('click', async () => {
    const url1 = document.getElementById('paper-url-1').value;
    const url2 = document.getElementById('paper-url-2').value;
    const statusElement = document.getElementById('paper-url-upload-status');

    const data = {
        paper_url_1: url1,
        paper_url_2: url2
    };

    try {
        const response = await fetch('/api/resources/upload/paper_url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        statusElement.textContent = result.message;
    } catch (error) {
        statusElement.textContent = '上传论文链接时出现错误';
    }
});

// 分析候选人
document.getElementById('analyze-btn').addEventListener('click', async () => {
    const statusElement = document.getElementById('analyze-status');
    const resultOutput = document.getElementById('result-output');

    try {
        const response = await fetch('/api/output/analyze', {
            method: 'GET'
        });
        const data = await response.json();

        if (data.status === 'success') {
            statusElement.textContent = '分析成功';
            resultOutput.textContent = JSON.stringify(data.data, null, 2);
        } else {
            statusElement.textContent = data.message;
        }
    } catch (error) {
        statusElement.textContent = '分析候选人时出现错误';
    }
});