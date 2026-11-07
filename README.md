# SensX25 Live — UNO Q / Arduino App Lab

添付のSensX25 Pythonサンプルに基づく、直接UART接続用アプリです。
matplotlibで数値入り5×5ヒートマップを描画し、WebUIで表示します。
目標更新速度は最大5回/秒です。UNO Qの負荷によって低下します。
全フレームの記録や無欠損収録を保証するものではありません。

## 配線

3.3V UARTタイプのSensX25を前提とします。電源電圧・線色・ピン順は
添付サンプルには記載がないため、実機の仕様書を確認してください。
RS-485の場合は直接接続できません。

| SensX25 | UNO Q |
| --- | --- |
| TX | D0 / RX |
| RX | D1 / TX（モード変更と読み戻しに必要） |
| GND | GND |
| VCC | センサー仕様で指定された電源 |

## App Labへの設定

1. 新規Appを作成するか、既存のTestServoを複製します。
2. Bricksから「WebUI - HTML」(`arduino:web_ui`)を追加します。
3. Sketch librariesにArduino_RouterBridgeとその依存ライブラリを追加します。
   以前のBridge版がビルドできたプロジェクトなら、それらを残してください。
4. このフォルダーと同じ構成で、以下のファイルをコピーします。
   - sketch/sketch.ino
   - sketch/sketch.yaml
   - python/main.py
   - python/requirements.txt
   - assets/index.html
5. 新規Appでは同梱のsketch/sketch.yamlを使用してください。
   以前提示された成功ログと同じUNO Qコア1.1.0、Bridge 0.4.4および依存ライブラリを指定しています。
6. Runを押し、WebUIのリンクを開きます。通常は http://<UNO-QのIP>:7000 です。
   PCのブラウザーにUNO QのIPを指定してください。PCのlocalhostではありません。

## 動作

- MCUがSerial1を921600bps / 8N1で読み、FF FF + 50バイト + CRC8のフレームを検証します。
- PythonはBridgeを通して最新の25点を読み、matplotlibのinfernoで描画します。
- センサーコネクターを下に向けた配置へ90度回転します。
- スケールはpressureで0～534、ADCで0～3945。範囲は元サンプルの記載値です。
- 起動時はレジスター0x6005を読みます。起動だけでは設定を書き換えません。
- ボタン操作時はModbus RTUの0x06で書き込み、0x03で読み戻して確認します。
- モードはセンサーに保存されます。同じモードへの重複書き込みは省きます。
- 切り替え中とデータ途絶中は数値を消し、古い値と新しいモードを混同させません。
- 単位はセンサー出力値です。Paなどの校正済み圧力への換算はしません。

## 問題がある場合

- Mode confirmation failed: RX→D1の配線、信号電圧、通信方式を確認します。
- NO RECENT DATA: TX→D0、共通GND、センサー電源を確認します。
- Communication error: Pythonログ、Sketchの起動、Bridgeライブラリを確認します。
- CRC errorsが増加: 配線長、接触、ノイズ、921600bpsの受信欠落を確認します。
- 色が表示されてもモードunknownの場合、モードの読み戻しは未確認です。

実機でのビルド・UART受信・モード切り替えは未検証です。
