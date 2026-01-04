import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls.Material 2.15

Window {
    id: debugWindow
    width: 520
    height: 760
    visible: false
    title: "Debug Console"
    color: "#0b0f17"
    flags: Qt.Dialog | Qt.WindowStaysOnTopHint

    property bool hasApp: typeof app !== "undefined" && app !== null
    property color panelColor: "#111722"
    property color borderColor: "#1f2a3a"
    property color accent: "#67d3ff"
    property int cardRadius: 16
    property int cardPadding: 14

    Material.theme: Material.Dark
    Material.accent: accent
    Material.foreground: "#e8edf5"

    function syncConfidence() {
        if (!hasApp) return;
        confSlider.value = app.confidence;
    }

    function batteryProfileIndex() {
        if (!hasApp) return 0;
        var target = app.bridgeBatteryProfileId;
        for (var i = 0; i < batteryProfileBox.model.length; i++) {
            if (batteryProfileBox.model[i].value === target) return i;
        }
        return 0;
    }

    Component.onCompleted: {
        syncConfidence();
        batteryProfileBox.currentIndex = batteryProfileIndex();
    }

    Shortcut {
        sequence: StandardKey.Close
        onActivated: debugWindow.visible = false
    }

    Connections {
        target: hasApp ? app : null
        function onConfidenceChanged() { syncConfidence(); }
        function onDetectorRunningChanged() { detectorSwitch.checked = app.detectorRunning }
        function onDebugModeChanged() { flightSwitch.checked = app.debugMode }
        function onSimCameraEnabledChanged() { cameraSimSwitch.checked = app.simCameraEnabled }
        function onBridgeModeChanged() { bridgeSwitch.checked = app.bridgeModeEnabled }
        function onBridgeBatteryProfileChanged() { batteryProfileBox.currentIndex = batteryProfileIndex(); }
        function onUnsafeStartChanged() { unsafeStartSwitch.checked = app.allowUnsafeStart }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: column.width
        contentHeight: column.height + 32
        clip: true

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
            id: column
            width: parent.width - 32
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 16
            spacing: 14

            Rectangle {
                width: parent.width
                implicitHeight: telemetryContent.implicitHeight + cardPadding * 2
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1

                Column {
                    id: telemetryContent
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 10

                    Text {
                        text: "Live telemetry"
                        color: "#e8edf5"
                        font.pixelSize: 16
                        font.family: "Inter"
                        font.bold: true
                    }

                    Flow {
                        width: parent.width
                        spacing: 12

                        Repeater {
                            model: [
                                { label: "FPS", value: function() { return hasApp ? app.fps.toFixed(1) : "n/a"; }, color: "#d7e0ec" },
                                { label: "Latency", value: function() { return hasApp ? (app.latencyMs.toFixed(0) + " ms") : "n/a"; }, color: "#d7e0ec" },
                                { label: "Detection conf", value: function() { return hasApp ? (app.detectionConfidence * 100).toFixed(1) + "%" : "0%"; }, color: "#7bc6ff" },
                                { label: "Bus", value: function() { return hasApp ? (app.busAlive ? "alive" : "idle") : "n/a"; }, color: hasApp && app.busAlive ? "#67e8a9" : "#fca5a5" },
                                { label: "Camera", value: function() { return hasApp ? (app.cameraAvailable ? "ready" : "missing") : "n/a"; }, color: hasApp && app.cameraAvailable ? "#c3f0ff" : "#f59e0b" },
                                { label: "Ground station", value: function() { return hasApp ? (app.groundStationEnabled ? "enabled" : "off") : "n/a"; }, color: hasApp && app.groundStationEnabled ? "#67e8a9" : "#fca5a5" },
                                { label: "Debug loop", value: function() { return hasApp ? Math.round(app.debugFlightProgress * 100) + "%" : "0%"; }, color: "#a5b4fc" }
                            ]
                            delegate: Rectangle {
                                width: 150
                                height: 62
                                radius: 12
                                color: "#0c111b"
                                border.color: borderColor
                                border.width: 1
                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 2
                                    Text {
                                        text: modelData.label
                                        color: "#94a3b8"
                                        font.pixelSize: 11
                                        font.family: "Inter"
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        text: modelData.value()
                                        color: modelData.color
                                        font.pixelSize: 15
                                        font.family: "Inter"
                                        font.weight: Font.Medium
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                implicitHeight: flightContent.implicitHeight + cardPadding * 2
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1

                Column {
                    id: flightContent
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 10

                    Text {
                        text: "Flight debug"
                        color: "#e8edf5"
                        font.pixelSize: 16
                        font.family: "Inter"
                        font.bold: true
                    }

                    Row {
                        width: parent.width
                        spacing: 12

                        Switch {
                            id: flightSwitch
                            text: flightSwitch.checked ? "Sim telemetry running" : "Sim telemetry stopped"
                            checked: hasApp && app.debugMode
                            onClicked: {
                                if (!hasApp) {
                                    checked = false
                                    return
                                }
                                app.setSimTelemetryEnabled(checked)
                            }
                        }

                        Switch {
                            id: cameraSimSwitch
                            text: cameraSimSwitch.checked ? "Sim camera on" : "Sim camera off"
                            checked: hasApp && app.simCameraEnabled
                            onClicked: {
                                if (!hasApp) {
                                    checked = false
                                    return
                                }
                                app.setSimCameraEnabled(checked)
                            }
                        }

                        Switch {
                            id: bridgeSwitch
                            text: bridgeSwitch.checked ? "Bridge mode on" : "Bridge mode off"
                            checked: hasApp && app.bridgeModeEnabled
                            onClicked: {
                                if (!hasApp) {
                                    checked = false
                                    return
                                }
                                app.setBridgeModeEnabled(checked)
                            }
                        }

                        Switch {
                            id: unsafeStartSwitch
                            text: unsafeStartSwitch.checked ? "Unsafe start on" : "Unsafe start off"
                            checked: hasApp && app.allowUnsafeStart
                            onClicked: {
                                if (!hasApp) {
                                    checked = false
                                    return
                                }
                                app.setAllowUnsafeStart(checked)
                            }
                        }

                        Button {
                            text: "Reset loop"
                            enabled: hasApp
                            onClicked: app.resetFlightDebugProgress()
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: 6

                        Text {
                            text: "Bridge battery profile"
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

                    ProgressBar {
                        width: parent.width
                        from: 0
                        to: 1
                        value: hasApp ? app.debugFlightProgress : 0
                        visible: hasApp
                    }

                    Flow {
                        width: parent.width
                        spacing: 10

                        Button { text: "Orbit preview"; enabled: hasApp; onClicked: app.recomputeOrbitPreview() }
                        Button { text: "Clear debug target"; enabled: hasApp; onClicked: app.clearDebugTarget() }
                        Button { text: "Regenerate map"; enabled: hasApp; onClicked: app.regenerateMap() }
                        Button { text: "Rebuild route"; enabled: hasApp; onClicked: app.rebuildRoute() }
                        Button { text: "Spawn object"; enabled: hasApp; onClicked: app.spawnConfirmedObject() }
                    }
                }
            }

            Rectangle {
                width: parent.width
                implicitHeight: mapContent.implicitHeight + cardPadding * 2
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1

                Column {
                    id: mapContent
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 10

                    Text {
                        text: "Planner & map provider"
                        color: "#e8edf5"
                        font.pixelSize: 16
                        font.family: "Inter"
                        font.bold: true
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        ComboBox {
                            id: mapProviderBox
                            width: parent.width - offlineSwitch.width - 12
                            model: [
                                { text: "OpenLayers (OSM DE)", value: "openlayers_de" },
                                { text: "OpenLayers (OSM HOT)", value: "openlayers_hot" },
                                { text: "OpenLayers (OSM FR)", value: "openlayers_osmfr" },
                                { text: "OpenLayers (OpenTopoMap)", value: "openlayers_topo" },
                                { text: "OpenLayers (Carto Light)", value: "openlayers_carto" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                        }

                        Switch {
                            id: offlineSwitch
                            text: "Offline cache"
                            checked: false
                        }
                    }

                    TextField {
                        id: cacheDirField
                        width: parent.width
                        placeholderText: "Cache dir"
                        text: hasApp ? app.tileCacheDir : ""
                    }

                    Flow {
                        width: parent.width
                        spacing: 10

                        Button {
                            text: "Apply provider"
                            enabled: hasApp
                            onClicked: {
                                if (!hasApp) return
                                app.setMapProvider(mapProviderBox.currentValue, offlineSwitch.checked, cacheDirField.text)
                                app.regenerateMap()
                                app.showToast("Map provider updated")
                            }
                        }
                        Button { text: "Orbit target"; enabled: hasApp; onClicked: app.orbitTarget() }
                    }
                }
            }

            Rectangle {
                width: parent.width
                implicitHeight: detectorContent.implicitHeight + cardPadding * 2
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1

                Column {
                    id: detectorContent
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 10

                    Text {
                        text: "Detector & camera"
                        color: "#e8edf5"
                        font.pixelSize: 16
                        font.family: "Inter"
                        font.bold: true
                    }

                    Row {
                        width: parent.width
                        spacing: 12

                        Switch {
                            id: detectorSwitch
                            text: detectorSwitch.checked ? "Detector running" : "Detector stopped"
                            checked: hasApp && app.detectorRunning
                            onClicked: {
                                if (!hasApp) {
                                    checked = false
                                    return
                                }
                                if (checked) app.startDetector()
                                else app.stopDetector()
                            }
                        }

                        Button { text: "Cycle camera"; enabled: hasApp; onClicked: app.cycleCamera() }
                    }

                    Column {
                        width: parent.width
                        spacing: 6

                        Text {
                            text: "Detection confidence: " + confSlider.value.toFixed(2)
                            color: "#d7e0ec"
                            font.pixelSize: 13
                            font.family: "Inter"
                        }

                        Slider {
                            id: confSlider
                            width: parent.width
                            from: 0.05
                            to: 0.9
                            stepSize: 0.01
                            onValueChanged: {
                                if (!hasApp) return
                                if (Math.abs(app.confidence - value) < 0.0001) return
                                app.setConfidence(value)
                            }
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                implicitHeight: actionsContent.implicitHeight + cardPadding * 2
                radius: cardRadius
                color: panelColor
                border.color: borderColor
                border.width: 1

                Column {
                    id: actionsContent
                    anchors.fill: parent
                    anchors.margins: cardPadding
                    spacing: 10

                    Text {
                        text: "Quick debug actions"
                        color: "#e8edf5"
                        font.pixelSize: 16
                        font.family: "Inter"
                        font.bold: true
                    }

                    Flow {
                        width: parent.width
                        spacing: 10

                        Button { text: "Ping toast"; enabled: hasApp; onClicked: app.showToast("Debug ping at " + new Date().toLocaleTimeString()) }
                        Button { text: "Reload map view"; enabled: hasApp; onClicked: app.regenerateMap() }
                        Button { text: "Close debug window"; onClicked: debugWindow.visible = false }
                    }
                }
            }
        }
    }
}
