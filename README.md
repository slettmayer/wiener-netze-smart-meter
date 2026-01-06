# Vienna Smart Meter Home Assistant Integration

The Vienna Smart Meter Integration allows you to integrate your smart electricity meter from Vienna into Home Assistant. 
This enables you to monitor and track data about your electricity consumption.

## Installation

1. Copy the `custom_components/wiener-netze-smart-meter` folder into the `custom_components` directory of your Home Assistant setup.
2. Restart Home Assistant
3. Configure the integration via the Home Assistant user interface or your `configuration.yaml` file.

## Configuration

Follow these steps to configure the integration:

1. Go to **Settings** -> **Integrations** in your Home Assistant user interface.
2. Click on the **+** icon to add a new integration.
3. Search for "Vienna Smart Meter" and select it.
4. Enter the required information:
    - **User (Geschäftspartner):** Your user ID for the smart meter.
    - **Device Number of Smart Meter (Zählpunktnummer):** The number of your smart electricity meter.
    - **KEYCLOAK_IDENTITY Cookie:** Visit https://smartmeter-web.wienernetze.at/ and copy the cookie from your browser's developer tools.
    - **Update Rate in Minutes:** Specify how often the electricity consumption should be loaded from the Vienna Smart Meter API.
    - **Optional:** Have you enabled the optional 15-minute timeframe in your Smart Meter configuration?
5. Follow the further instructions in the user interface to complete the configuration.

## Usage

Once the integration is configured, sensors for your electricity consumption will be automatically created in Home Assistant. You can use these sensors in your dashboards to monitor your electricity consumption.

## Support

If you need assistance with configuring or using the Vienna Smart Meter Integration, feel free to contact us.
