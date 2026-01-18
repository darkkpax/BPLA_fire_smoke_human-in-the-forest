import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls.Material 2.15

Window {
    id: debugWindow
    width: 480
    height: 360
    visible: false
    title: "Bridge console"
    color: "#0b0f17"
    flags: Qt.Dialog | Qt.WindowStaysOnTopHint

    property bool hasApp: typeof app !== "undefined" && app !== null
    property color panelColor: "#111722"
    property color borderColor: "#1f2a3a"
    property color accent: "#67d3ff"
    property int cardRadius: 16
    property int cardPadding: 16

    Material.theme: Material.Dark
    Material.accent: accent
    Material.foreground: "#e8edf5"

    function batteryProfileIndex() {
        if (!hasApp) return 0
        var target = app.bridgeBatteryProfileId
        var model = batteryProfileBox ? batteryProfileBox.model : []
        for (var i = 0; i < model.length; i++) {
            if (model[i].value === target) return i
        }
        return 0
    }

    Component.onCompleted: {
        batteryProfileBox.currentIndex = batteryProfileIndex()
    }

    Shortcut {
        sequence: StandardKey.Close
        onActivated: debugWindow.visible = false
    }

    Connections {
        target: hasApp ? app : null
        function onBridgeBatteryProfileChanged() {
            if (!batteryProfileBox) return
            batteryProfileBox.currentIndex = batteryProfileIndex()
        }
        function onBridgeModeChanged() {
            bridgeSwitch.checked = hasApp && app.bridgeModeEnabled
        }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: parent.width
        contentHeight: bridgeCard.implicitHeight + cardPadding * 2
        clip: true

        Column {
            id: column
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 16
            spacing: 16

            Rectangle {
                id: bridgeCard
                width: parent.width - 32
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1
                anchors.horizontalCenter: parent.horizontalCenter

                Column {
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 12

                    Text {
                        text: "Bridge mode controls"
                        color: "#e8edf5"
                        font.pixelSize: 18
                        font.family: "Inter"
                        font.bold: true
                    }

                    Text {
                        text: "Toggle this switch to simulate the real UAV pipeline (telemetry + camera) and pick a drone profile."
                        color: "#94a3b8"
                        font.pixelSize: 12
                        font.family: "Inter"
                        wrapMode: Text.WordWrap
                    }

                    Switch {
                        id: bridgeSwitch
                        checked: hasApp && app.bridgeModeEnabled
                        text: checked ? "Bridge mode (simulate real UAV) ON" : "Bridge mode OFF"
                        enabled: hasApp
                        onClicked: {
                            if (!hasApp) {
                                checked = false
                                return
                            }
                            app.setBridgeModeEnabled(checked)
                        }
                        onToggled: {
                            if (!hasApp) {
                                checked = false
                                return
                            }
                            app.setBridgeModeEnabled(checked)
                        }
                    }

                    Column {
                        spacing: 6

                        Text {
                            text: "Drone profile"
                            color: "#94a3b8"
                            font.pixelSize: 12
                            font.family: "Inter"
                        }

                        ComboBox {
                            id: batteryProfileBox
                            width: parent.width
                            model: [
                                { text: "DJI Mavic 3 (77 Wh)", value: "mavic3" },
                                { text: "DJI Mini 4 Pro (29 Wh)", value: "mini4" },
                                { text: "DJI Matrice 30T (263 Wh)", value: "matrice30" },
                                { text: "Autel EVO II (82 Wh)", value: "autel_evo" },
                                { text: "Skydio X2 (49 Wh)", value: "skydio_x2" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                            onActivated: {
                                if (!hasApp) return
                                app.setBridgeBatteryProfile(currentValue)
                            }
                        }
                    }

                    Button {
                        text: "Close debug window"
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width * 0.6
                        onClicked: debugWindow.visible = false
                    }
                }
            }
        }
    }
}
