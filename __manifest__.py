{
    'name': 'RapidAPI Bdeel',
    'version': '1.1',
    'category': 'Sales',
    'summary': 'Integration with TecDoc RapidAPI',
    'author': 'Bdeel',
    'depends': ['base', 'product', 'sale', 'website_sale'],
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
