
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎵 Формат музичних постів</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            max-width: 800px;
            width: 100%;
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #1DB954, #191414);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .content {
            padding: 40px;
        }
        
        .format-section {
            margin-bottom: 30px;
        }
        
        .format-title {
            color: #191414;
            font-size: 1.4em;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .format-title::before {
            content: "📝";
            margin-right: 10px;
        }
        
        .format-box {
            background: #f8f9fa;
            border: 2px dashed #1DB954;
            border-radius: 10px;
            padding: 20px;
            font-family: 'Courier New', monospace;
            font-size: 1.1em;
            margin-bottom: 15px;
        }
        
        .highlight {
            background: #1DB954;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        .example {
            background: #e8f5e8;
            border-left: 4px solid #1DB954;
            padding: 20px;
            border-radius: 0 10px 10px 0;
            margin: 20px 0;
        }
        
        .example-title {
            color: #1DB954;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 1.1em;
        }
        
        .rules {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 10px;
            padding: 20px;
            margin-top: 30px;
        }
        
        .rules h3 {
            color: #856404;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .rules h3::before {
            content: "⚠️";
            margin-right: 10px;
        }
        
        .rule-item {
            margin-bottom: 10px;
            padding-left: 20px;
            position: relative;
        }
        
        .rule-item::before {
            content: "•";
            color: #856404;
            font-weight: bold;
            position: absolute;
            left: 0;
        }
        
        .footer {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e9ecef;
        }
        
        .spotify-logo {
            color: #1DB954;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎵 Музичний бот</h1>
            <p>Інструкція з форматування постів для автоматичного пошуку музики в Spotify</p>
        </div>
        
        <div class="content">
            <div class="format-section">
                <h2 class="format-title">Правильний формат запису</h2>
                <div class="format-box">
                    Будь-який текст <span class="highlight">#music</span> ще якийсь текст <span class="highlight">(Виконавець - Назва треку/альбому)</span>
                </div>
                <p>Ваш пост повинен містити хештег <strong>#music</strong> та назву музики в круглих дужках у форматі <strong>Виконавець - Назва</strong></p>
            </div>
            
            <div class="example">
                <div class="example-title">✅ Приклади правильного форматування:</div>
                <p><strong>Пост 1:</strong><br>
                Сьогодні слухаю класну музику! #music Дуже рекомендую всім послухати (The Weeknd - Blinding Lights)</p>
                
                <p style="margin-top: 15px;"><strong>Пост 2:</strong><br>
                #music Знайшов новий альбом (Imagine Dragons - Mercury)</p>
                
                <p style="margin-top: 15px;"><strong>Пост 3:</strong><br>
                Неймовірна пісня! #music Всім радю (Billie Eilish - Bad Guy) ❤️</p>
            </div>
            
            <div class="example" style="background: #ffe6e6; border-left-color: #dc3545;">
                <div class="example-title" style="color: #dc3545;">❌ Приклади неправильного форматування:</div>
                <p><strong>Помилка 1:</strong> Слухаю музику The Weeknd - Blinding Lights <em>(немає #music та круглих дужок)</em></p>
                
                <p style="margin-top: 10px;"><strong>Помилка 2:</strong> #music The Weeknd - Blinding Lights <em>(немає круглих дужок)</em></p>
                
                <p style="margin-top: 10px;"><strong>Помилка 3:</strong> #music (The Weeknd Blinding Lights) <em>(немає тире між виконавцем та назвою)</em></p>
            </div>
            
            <div class="rules">
                <h3>Важливі правила</h3>
                <div class="rule-item">Обов'язково використовуйте хештег <strong>#music</strong></div>
                <div class="rule-item">Назва музики має бути в круглих дужках <strong>( )</strong></div>
                <div class="rule-item">Формат: <strong>Виконавець - Назва треку/альбому</strong></div>
                <div class="rule-item">Між виконавцем та назвою обов'язково має бути <strong>тире (-)</strong></div>
                <div class="rule-item">Регістр не важливий: #music, #Music, #MUSIC - все працює</div>
                <div class="rule-item">Можете додавати будь-який текст до та після обов'язкових елементів</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Бот автоматично знайде музику в <span class="spotify-logo">Spotify</span> та надішле красиву картку з посиланням!</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
