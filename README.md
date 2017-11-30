Зависимости отсутствуют, порт по умолчанию - `9090`. Справка по использованию:

```
usage: runserver.py [-h] [--port [PORT]]

Habraproxy.

optional arguments:
  -h, --help     show this help message and exit
  --port [PORT]  local port for proxy server

```

# Задание

Реализовать простой http-прокси-сервер, запускаемый локально (порт на ваше усмотрение), который показывает содержимое страниц Хабра. Прокси должен модицифировать текст на страницах следующим образом: после каждого слова из шести букв должен стоять значок «™».

# Условия:
 * Python 3.5+
 * Страницы должны отображаться и работать полностью корректно, в точности так, как и оригинальные (за исключением модифицированного текста)
 * При навигации по ссылкам, которые ведут на другие страницы хабра, браузер должен оставаться на адресе вашего прокси
 * PEP8 — обязательно
