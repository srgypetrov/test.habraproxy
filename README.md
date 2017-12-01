Зависимости отсутствуют, контент страницы модифицируется только при наличии заголовков `Content-Encoding: gzip` и `Content-Type: text/html; charset=utf-8` в ответе.

Справка по использованию:

```
usage: runserver.py [-h] [-l [PORT]] [-t [HOST]] [-p [PORT]]

Habraproxy

optional arguments:
  -h, --help            show this help message and exit
  -l [PORT], --local-port [PORT]
                        proxy server local port
  -t [HOST], --target-host [HOST]
                        proxy server target host name
  -p [PORT], --target-port [PORT]
                        proxy server target port.

```

Значения по умолчанию:
  * local-port - `9090`
  * target-host - `habrahabr.ru`
  * target-port - `443`

Пример использования:

```
python runserver.py -l 9999 -t django-rest-framework.org -p 80
```

# Задание

Реализовать простой http-прокси-сервер, запускаемый локально (порт на ваше усмотрение), который показывает содержимое страниц Хабра. Прокси должен модицифировать текст на страницах следующим образом: после каждого слова из шести букв должен стоять значок «™».

# Условия:
 * Python 3.5+
 * Страницы должны отображаться и работать полностью корректно, в точности так, как и оригинальные (за исключением модифицированного текста)
 * При навигации по ссылкам, которые ведут на другие страницы хабра, браузер должен оставаться на адресе вашего прокси
 * PEP8 — обязательно
