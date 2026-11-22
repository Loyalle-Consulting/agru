# -*- coding: utf-8 -*-
{
    'name': 'AGRU - Selector Visual de Moneda (Sitio Web)',
    'version': '19.0.2.0.0',
    'category': 'Website/Website',
    'summary': 'Selector CLP/USD puramente visual en la tienda online: los precios '
               'se muestran en la moneda elegida, pero el carrito y el pago siempre '
               'quedan en la moneda real de la tienda.',
    'description': """
AGRU - Selector Visual de Moneda (Sitio Web)
=================================================
Agrega un selector de moneda CLP/USD en el encabezado del sitio web. Al
elegir una moneda, los precios mostrados en la tienda, ficha de
producto y carrito cambian de inmediato (sin recargar la página),
calculados con la tasa de cambio oficial del día.

CLP y USD son un par FIJO: no dependen de qué lista de precios esté
activa en la sesión del visitante. El selector siempre compara la
moneda en la que la página ya está mostrando los precios (que sí sigue
a la lista de precios activa: Público general -> CLP, Instaladores ->
USD, etc.) contra la otra moneda del par, así el botón aparece siempre,
sin importar en qué moneda esté la lista que el cliente está viendo.

IMPORTANTE: esto es puramente visual/informativo. El carrito, el
checkout y el pago SIEMPRE se procesan en la moneda real configurada en
el sitio web (ej. CLP) — nunca se modifica currency_id del pedido ni de
la lista de precios. No reemplaza ni interactúa con el módulo de
totalización de cotizaciones del backoffice (agru_sale_currency_lock).

Changelog 19.0.1.1.0: antes el selector comparaba la moneda de la
página contra una moneda "secundaria" configurable (parámetro de
sistema, default USD), y se ocultaba por completo cuando ambas
coincidían — lo cual pasaba justo en las listas de precio ya
denominadas en USD (ej. Instaladores), que eran la mayoría. Se
reemplaza esa lógica por un par fijo CLP/USD: el botón ahora aparece
siempre, comparando lo que la página muestra contra la otra moneda del
par. Ya no se usa el parámetro de sistema
'agru_website_currency_toggle.secondary_currency'.

Changelog 19.0.1.2.0: dos fixes.
1) Doble conversión en /shop/cart — el precio de cada línea ahí ya
   viene forzado a CLP por agru_sale_currency_lock_website, sin
   importar de qué lista salió el producto. En esa ruta puntual la
   moneda base del toggle ahora siempre es CLP (antes se guiaba por la
   lista de precios como en cualquier otra página, causando que un
   monto ya en pesos se multiplicara otra vez por la tasa).
2) Ficha de producto mostrando el símbolo convertido pero el monto sin
   convertir — la ficha vuelve a pedir el precio por AJAX después de
   cargar y sobrescribe solo el texto del número; ahora el JS también
   detecta ese tipo de cambio y reconvierte.

Changelog 19.0.1.3.0: dos fixes más.
1) En /shop/cart el toggle mostraba las dos monedas iguales ("USD USD")
   — la plantilla calculaba el símbolo principal leyendo
   website.currency_id directo, sin pasar por la lógica que ya sabía
   que el carrito es un caso especial (siempre CLP). Ahora el backend
   devuelve la moneda principal EFECTIVA junto con la secundaria, y la
   plantilla usa ese mismo valor para ambos símbolos.
2) Después de ir y volver entre monedas, a veces quedaba un símbolo
   viejo pegado a un monto nuevo. Se eliminó la idea de guardar y
   restaurar HTML: ahora se guarda solo el monto numérico puro y el
   HTML se reconstruye desde cero cada vez.
""",
    'author': 'Loyalle Consulting',
    'website': 'https://www.grupoloyalle.cl',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'agru_website_currency_toggle/static/src/js/currency_toggle.js',
            'agru_website_currency_toggle/static/src/css/currency_toggle.css',
        ],
    },
    'installable': True,
    'application': False,
}
