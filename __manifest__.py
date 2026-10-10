{
    'name': 'Odoo OEM Connect',
    'version': '18.0.1.2.0',
    'category': 'Sales',
    'summary': 'Integration with TecDoc RapidAPI',
    'author': 'Bdeel',
    'license': 'OPL-1',
    'depends': ['base', 'product', 'stock', 'delivery', 'sale', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/tecdoc_part_views.xml',
        'views/tecdoc_template.xml',
        'views/product_template_views.xml',
        'views/tecdoc_api_log_views.xml',
        'views/tecdoc_import_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/tecdoc_vehicle_views.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'rapidapi_bdeel/static/src/js/tecdoc_resizable.js',
        ]
    },
    'installable': True,
    'application': True,
}
