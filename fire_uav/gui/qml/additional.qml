import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtWebEngine 1.10
import Qt5Compat.GraphicalEffects

ApplicationWindow {
    id: root
    width: 1600
    height: 940
    minimumWidth: 1280
    minimumHeight: 760
    visible: true
    title: "fire_uav // tactical"
    color: "#000000"

    property bool hasApp: typeof app !== "undefined" && app !== null
    property color pageBg: "#000000"
    property color panelBg: "#151515"
    property color panelBgSoft: "#1c1c1c"
    property color panelInset: "#222222"
    property color textPrimary: "#edf3f7"
    property color textMuted: "#9aa7b5"
    property color accent: "#7bc6ff"
    property color accentStrong: "#f7b55c"
    property color borderColor: Qt.rgba(1, 1, 1, 0.10)
    property color borderSoft: Qt.rgba(1, 1, 1, 0.06)
    property color mapGlassFill: Qt.rgba(0.08, 0.08, 0.08, 0.58)
    property color mapGlassFillStrong: Qt.rgba(0.08, 0.08, 0.08, 0.72)
    property color mapGlassBorder: Qt.rgba(1, 1, 1, 0.14)
    property color mapGlassShadow: Qt.rgba(0, 0, 0, 0.24)
    property bool homePickModeActive: hasApp ? app.homePickModeEnabled : false
    property bool manualTargetModeActive: hasApp ? app.objectSpawnModeEnabled : false
    property bool showVideoFeed: true
    property bool toastVisible: false
    property string toastText: ""
    property var pendingConsoleMessages: []
    property bool mapBridgeInjected: false

    function runMapTool(name, arg) {
        if (!mapView) return;
        var callArg = (arg === undefined) ? "" : JSON.stringify(arg);
        var js = "window.__mapTools && window.__mapTools." + name
               + " && window.__mapTools." + name + "(" + callArg + ")";
        mapView.runJavaScript(js);
    }

    function missionTone() {
        if (!hasApp) return "#9aa7b5";
        if (app.missionState === "IN_FLIGHT") return "#7bc6ff";
        if (app.missionState === "RTL") return "#f7b55c";
        if (app.missionState === "POSTFLIGHT") return "#78d79a";
        return "#d9e1e8";
    }

    function showToastMessage(message) {
        toastText = message;
        toastVisible = true;
        toastTimer.restart();
    }

    Timer {
        id: toastTimer
        interval: 2600
        repeat: false
        onTriggered: root.toastVisible = false
    }

    Connections {
        target: hasApp ? app : null
        function onToastRequested(message) { root.showToastMessage(message); }
        function onFrameReady(url) { videoView.source = url; }
    }

    Rectangle {
        anchors.fill: parent
        color: pageBg
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: Qt.rgba(1, 1, 1, 0.04)
        border.width: 1
    }

    component GlassButton: Item {
        id: glassButtonRoot
        property string label: ""
        property var action
        property bool accentButton: false
        property bool warningButton: false
        property bool hovered: false
        property bool pressed: false
        property bool enabled: true
        property int px: 13
        implicitWidth: Math.max(96, labelText.implicitWidth + 28)
        implicitHeight: 40
        opacity: enabled ? 1.0 : 0.42
        scale: pressed && enabled ? 0.985 : 1.0
        clip: true
        layer.enabled: true
        layer.smooth: true
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            radius: 14
            clip: true
            antialiasing: true
            color: warningButton
                   ? Qt.rgba(0.22, 0.08, 0.07, glassButtonRoot.hovered ? 0.88 : 0.80)
                   : accentButton
                     ? Qt.rgba(0.10, 0.20, 0.28, glassButtonRoot.hovered ? 0.86 : 0.78)
                     : Qt.rgba(0.14, 0.14, 0.14, glassButtonRoot.hovered ? 0.82 : 0.74)
            border.color: warningButton
                          ? Qt.rgba(1.0, 0.62, 0.58, 0.20)
                          : accentButton
                            ? Qt.rgba(0.73, 0.89, 1.0, 0.16)
                            : borderColor
            border.width: 1
        }

        Text {
            id: labelText
            anchors.centerIn: parent
            text: glassButtonRoot.label
            color: textPrimary
            font.pixelSize: glassButtonRoot.px
            font.family: "Inter"
            font.bold: accentButton || warningButton || glassButtonRoot.hovered
        }

        MouseArea {
            anchors.fill: parent
            enabled: glassButtonRoot.enabled
            hoverEnabled: true
            onEntered: glassButtonRoot.hovered = true
            onExited: {
                glassButtonRoot.hovered = false;
                glassButtonRoot.pressed = false;
            }
            onPressed: glassButtonRoot.pressed = true
            onReleased: glassButtonRoot.pressed = false
            onClicked: if (glassButtonRoot.action) glassButtonRoot.action()
        }
    }

    component StatChip: Rectangle {
        property string chipLabel: ""
        property string chipValue: ""
        property color valueColor: textPrimary
        implicitWidth: Math.max(112, chipColumn.implicitWidth + 22)
        implicitHeight: 48
        radius: 16
        color: panelBgSoft
        border.color: borderSoft
        border.width: 1
        clip: true
        antialiasing: true
        layer.enabled: true
        layer.smooth: true

        Column {
            id: chipColumn
            anchors.centerIn: parent
            spacing: 2

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: chipLabel
                color: textMuted
                font.pixelSize: 11
                font.family: "Inter"
                font.letterSpacing: 1.2
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: chipValue
                color: valueColor
                font.pixelSize: 16
                font.family: "Inter"
                font.bold: true
            }
        }
    }

    component SectionCard: Rectangle {
        radius: 22
        color: panelBg
        border.color: borderColor
        border.width: 1
        clip: true
        antialiasing: true
        layer.enabled: true
        layer.smooth: true
    }

    component MapGlassPane: Rectangle {
        id: mapGlassPane
        property Item blurSource: null
        property var blurOrigin: blurSource ? mapGlassPane.mapToItem(blurSource, 0, 0) : Qt.point(0, 0)
        radius: 20
        color: mapGlassFill
        border.color: mapGlassBorder
        border.width: 1
        clip: true
        antialiasing: true
        layer.enabled: true
        layer.smooth: true

        ShaderEffectSource {
            id: mapGlassSlice
            anchors.fill: parent
            sourceItem: mapGlassPane.blurSource
            sourceRect: Qt.rect(mapGlassPane.blurOrigin.x, mapGlassPane.blurOrigin.y, mapGlassPane.width, mapGlassPane.height)
            recursive: true
            live: root.visible && !!mapGlassPane.blurSource
            visible: false
        }

        FastBlur {
            id: mapGlassBlur
            anchors.fill: parent
            source: mapGlassSlice
            radius: 16
            transparentBorder: true
            visible: !!mapGlassPane.blurSource
            z: -3
        }

        OpacityMask {
            anchors.fill: parent
            source: mapGlassBlur
            maskSource: Rectangle {
                width: mapGlassPane.width
                height: mapGlassPane.height
                radius: mapGlassPane.radius
            }
            z: -2
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            anchors.bottomMargin: 2
            height: 1
            radius: 1
            antialiasing: true
            color: "transparent"
            border.color: Qt.rgba(0, 0, 0, 0.18)
            border.width: 1
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 78
            radius: 24
            color: panelBg
            border.color: borderColor
            border.width: 1
            clip: true

            RowLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 14

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    StatChip {
                        chipLabel: "STATE"
                        chipValue: hasApp ? app.missionState : "--"
                        valueColor: root.missionTone()
                    }

                    StatChip {
                        chipLabel: "BATTERY"
                        chipValue: hasApp ? app.currentBatteryText.replace("Battery: ", "") : "--"
                        valueColor: hasApp && app.routeBatteryWarning ? "#ff9a86" : textPrimary
                    }

                    StatChip {
                        chipLabel: "FPS"
                        chipValue: hasApp ? app.fps.toFixed(1) : "0.0"
                        valueColor: accent
                    }

                    StatChip {
                        chipLabel: "CONF"
                        chipValue: hasApp ? (Math.round(app.detectionConfidence * 100) + "%") : "0%"
                        valueColor: accentStrong
                    }

                    StatChip {
                        chipLabel: "TARGETS"
                        chipValue: hasApp ? String(app.confirmedObjectCount) : "0"
                        valueColor: "#ffc874"
                    }
                }

                Item {
                    Layout.preferredWidth: root.showVideoFeed ? 0 : showCameraButton.implicitWidth
                    Layout.fillHeight: true

                    GlassButton {
                        id: showCameraButton
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.right: parent.right
                        visible: !root.showVideoFeed
                        label: "Show camera"
                        action: function() { root.showVideoFeed = true; }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            ScrollView {
                Layout.preferredWidth: 320
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    width: parent.width
                    spacing: 12

                    SectionCard {
                        Layout.fillWidth: true
                        implicitHeight: actionCardColumn.implicitHeight + 30

                        ColumnLayout {
                            id: actionCardColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            Text {
                                text: "Controls"
                                color: textPrimary
                                font.pixelSize: 18
                                font.family: "Inter"
                                font.bold: true
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: 8
                                rowSpacing: 8

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Detector on"
                                    action: function() { if (hasApp) app.startDetector(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Save plan"
                                    action: function() { if (hasApp) app.savePlan(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: hasApp && app.routeEditMode ? "Apply route" : "Edit route"
                                    accentButton: hasApp && app.routeEditMode
                                    action: function() {
                                        if (!hasApp) return;
                                        if (app.routeEditMode) app.applyRouteEdits();
                                        else app.editRoute();
                                    }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Cancel edit"
                                    enabled: hasApp ? app.canCancelRouteEdits : false
                                    action: function() { if (hasApp) app.cancelRouteEdits(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Confirm plan"
                                    accentButton: true
                                    enabled: hasApp ? app.canConfirmPlan : false
                                    action: function() { if (hasApp) app.confirmPlan(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Orbit target"
                                    enabled: hasApp ? app.canOpenOrbit : false
                                    action: function() { if (hasApp) app.orbitConfirmedObject(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Send RTL path"
                                    enabled: hasApp ? app.canSendRtlRoute : false
                                    action: function() { if (hasApp) app.sendRtlRoute(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Return home"
                                    warningButton: true
                                    enabled: hasApp ? app.canRtl : false
                                    action: function() { if (hasApp) app.returnToHome(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Land"
                                    enabled: hasApp ? app.canCompleteLanding : false
                                    action: function() { if (hasApp) app.completeLanding(); }
                                }

                                GlassButton {
                                    Layout.fillWidth: true
                                    label: "Preflight"
                                    enabled: hasApp ? app.canAbortToPreflight : false
                                    action: function() { if (hasApp) app.abortToPreflight(); }
                                }
                            }
                        }
                    }

                    SectionCard {
                        Layout.fillWidth: true
                        implicitHeight: telemetryColumn.implicitHeight + 30

                        ColumnLayout {
                            id: telemetryColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 8

                            Text {
                                text: "Telemetry"
                                color: textPrimary
                                font.pixelSize: 18
                                font.family: "Inter"
                                font.bold: true
                            }

                            Text {
                                text: hasApp ? ("Latency " + app.latencyMs.toFixed(0) + " ms") : "Latency --"
                                color: textPrimary
                                font.pixelSize: 13
                                font.family: "Inter"
                            }

                            Text {
                                text: hasApp ? ("Camera " + app.cameraStatusDetail) : "Camera --"
                                color: textMuted
                                font.pixelSize: 12
                                font.family: "Inter"
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            Text {
                                text: hasApp ? ("Backend status " + app.unrealRuntimeStatus) : "Backend --"
                                color: textMuted
                                font.pixelSize: 12
                                font.family: "Inter"
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                SectionCard {
                    anchors.fill: parent
                }

                Item {
                    id: stageLayer
                    anchors.fill: parent
                    anchors.margins: 12
                    clip: true

                    Rectangle {
                        anchors.fill: parent
                        radius: 20
                        color: "#090909"
                        border.color: Qt.rgba(1, 1, 1, 0.05)
                        border.width: 1
                        clip: true
                    }

                    WebEngineView {
                        id: mapView
                        anchors.fill: parent
                        anchors.margins: 4
                        url: hasApp ? app.mapUrl : ""
                        clip: true
                        settings.localContentCanAccessFileUrls: true
                        settings.localContentCanAccessRemoteUrls: true
                        settings.javascriptCanOpenWindows: false

                        onLoadingChanged: function(loadRequest) {
                            if (loadRequest.status === WebEngineView.LoadStartedStatus) {
                                root.mapBridgeInjected = false;
                                root.pendingConsoleMessages = [];
                            } else if (loadRequest.status === WebEngineView.LoadSucceededStatus) {
                                root.mapBridgeInjected = true;
                                if (hasApp) {
                                    mapView.runJavaScript(app.mapBridgeScript);
                                    for (var i = 0; i < root.pendingConsoleMessages.length; i++) {
                                        app.handleMapConsole(root.pendingConsoleMessages[i]);
                                    }
                                }
                                root.pendingConsoleMessages = [];
                            }
                        }

                        onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {
                            if (!root.mapBridgeInjected) {
                                root.pendingConsoleMessages.push(message);
                                return;
                            }
                            if (hasApp) app.handleMapConsole(message);
                            if (level === WebEngineView.ErrorMessageLevel) {
                                console.error("Map JS error", message, lineNumber, sourceID);
                            }
                        }
                    }

                    MapGlassPane {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 18
                        height: 60
                        blurSource: mapView
                        color: mapGlassFillStrong

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 8

                            GlassButton {
                                label: "Draw path"
                                action: function() { root.runMapTool("drawPath"); }
                            }

                            GlassButton {
                                label: "Remove"
                                action: function() { root.runMapTool("setRemoveMode", true); }
                            }

                            GlassButton {
                                label: "Reset"
                                action: function() { root.runMapTool("resetView"); }
                            }

                            GlassButton {
                                label: "Regenerate"
                                action: function() { if (hasApp) app.regenerateMap(); }
                            }

                            GlassButton {
                                label: "Refresh map"
                                action: function() { if (hasApp) app.refreshMapView(); }
                            }

                            Item { Layout.fillWidth: true }
                        }
                    }

                    Item {
                        id: mapClickOverlay
                        anchors.fill: parent
                        visible: homePickModeActive || manualTargetModeActive
                        z: 4

                        MouseArea {
                            anchors.fill: parent
                            enabled: mapClickOverlay.visible
                            acceptedButtons: Qt.LeftButton
                            onClicked: {
                                var script = "window.__mapTools && window.__mapTools.screenToGeo(" + mouse.x + "," + mouse.y + ")";
                                mapView.runJavaScript(script, function(result) {
                                    if (!result || typeof result.lat !== "number" || typeof result.lon !== "number") return;
                                    if (homePickModeActive && hasApp) app.setHomeFromMap(result.lat, result.lon);
                                    if (manualTargetModeActive && hasApp) app.spawnManualTargetAt(result.lat, result.lon);
                                });
                            }
                        }
                    }

                    MapGlassPane {
                        id: videoDock
                        width: root.showVideoFeed ? Math.min(parent.width * 0.32, 360) : 0
                        height: root.showVideoFeed ? 214 : 0
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: 18
                        radius: 20
                        blurSource: mapView
                        color: mapGlassFillStrong
                        visible: root.showVideoFeed

                        Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }
                        Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                        Image {
                            id: videoView
                            anchors.fill: parent
                            fillMode: Image.PreserveAspectCrop
                            cache: false
                            smooth: true
                            source: hasApp && app.cameraAvailable ? "image://video/live" : ""
                            visible: hasApp && app.cameraAvailable
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: Qt.rgba(0, 0, 0, 0.58)
                            visible: (!hasApp || !app.cameraAvailable) || videoView.status !== Image.Ready
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 48
                            color: Qt.rgba(0.04, 0.04, 0.04, 0.72)
                            clip: true

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 8

                                Text {
                                    Layout.fillWidth: true
                                    text: hasApp ? app.cameraStatusDetail : "Camera offline"
                                    color: textPrimary
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                    elide: Text.ElideRight
                                }

                                GlassButton {
                                    label: "Hide camera"
                                    px: 12
                                    implicitWidth: 112
                                    implicitHeight: 32
                                    action: function() { root.showVideoFeed = false; }
                                }
                            }
                        }
                    }

                    MapGlassPane {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: 18
                        anchors.rightMargin: videoDock.visible ? (videoDock.width + 30) : 18
                        height: 110
                        radius: 18
                        blurSource: mapView
                        color: mapGlassFillStrong

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    text: "Targets in scene"
                                    color: textPrimary
                                    font.pixelSize: 16
                                    font.family: "Inter"
                                    font.bold: true
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    text: hasApp ? (String(app.confirmedObjectCount) + " tracked") : "0 tracked"
                                    color: textMuted
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                }
                            }

                            ListView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                orientation: ListView.Horizontal
                                spacing: 10
                                clip: true
                                model: hasApp ? app.confirmedObjects : []

                                delegate: Rectangle {
                                    width: 170
                                    height: 58
                                    radius: 14
                                    color: modelData.selected ? Qt.rgba(0.22, 0.34, 0.44, 0.44) : Qt.rgba(1, 1, 1, 0.05)
                                    border.color: modelData.selected ? Qt.rgba(0.73, 0.89, 1.0, 0.22) : borderSoft
                                    border.width: 1
                                    clip: true

                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 3

                                        Text {
                                            text: modelData.object_id
                                            color: textPrimary
                                            font.pixelSize: 12
                                            font.family: "Inter"
                                            font.bold: true
                                            elide: Text.ElideRight
                                            width: parent.width
                                        }

                                        Text {
                                            text: (modelData.label || "target") + "  •  conf " + Number(modelData.confidence || 0).toFixed(2)
                                            color: textMuted
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: if (hasApp) app.selectConfirmedObject(modelData.object_id)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            ScrollView {
                Layout.preferredWidth: 320
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    width: parent.width
                    spacing: 12

                    SectionCard {
                        Layout.fillWidth: true
                        implicitHeight: targetsColumn.implicitHeight + 30

                        ColumnLayout {
                            id: targetsColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            Text {
                                text: "Detected objects"
                                color: textPrimary
                                font.pixelSize: 18
                                font.family: "Inter"
                                font.bold: true
                            }

                            Repeater {
                                model: hasApp ? app.confirmedObjects : []

                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    width: targetsColumn.width
                                    radius: 16
                                    color: modelData.selected ? Qt.rgba(0.22, 0.34, 0.44, 0.34) : Qt.rgba(1, 1, 1, 0.05)
                                    border.color: modelData.selected ? Qt.rgba(0.73, 0.89, 1.0, 0.22) : borderSoft
                                    border.width: 1
                                    implicitHeight: targetInfo.implicitHeight + 20
                                    clip: true

                                    Column {
                                        id: targetInfo
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 4

                                        Text {
                                            text: modelData.object_id
                                            color: textPrimary
                                            font.pixelSize: 13
                                            font.family: "Inter"
                                            font.bold: true
                                        }

                                        Text {
                                            text: (modelData.label || "target") + "  •  confidence " + Number(modelData.confidence || 0).toFixed(2)
                                            color: textMuted
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                        }

                                        Text {
                                            text: "Lat " + Number(modelData.lat || 0).toFixed(5) + "  Lon " + Number(modelData.lon || 0).toFixed(5)
                                            color: "#cfe2ee"
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: if (hasApp) app.selectConfirmedObject(modelData.object_id)
                                    }
                                }
                            }

                            Text {
                                visible: hasApp && app.confirmedObjectCount === 0
                                text: "Confirmed targets will appear here after detection or manual spawn."
                                color: textMuted
                                font.pixelSize: 12
                                font.family: "Inter"
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }

                    SectionCard {
                        Layout.fillWidth: true
                        implicitHeight: logColumn.implicitHeight + 30

                        ColumnLayout {
                            id: logColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            Text {
                                text: "System log"
                                color: textPrimary
                                font.pixelSize: 18
                                font.family: "Inter"
                                font.bold: true
                            }

                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 360
                                clip: true
                                model: hasApp ? app.logs : []
                                spacing: 6

                                delegate: Rectangle {
                                    width: logColumn.width
                                    radius: 12
                                    color: Qt.rgba(1, 1, 1, 0.04)
                                    border.color: borderSoft
                                    border.width: 1
                                    implicitHeight: logText.implicitHeight + 18
                                    clip: true

                                    Text {
                                        id: logText
                                        anchors.fill: parent
                                        anchors.margins: 9
                                        text: modelData
                                        color: textMuted
                                        font.pixelSize: 11
                                        font.family: "Consolas"
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                ScrollBar.vertical: ScrollBar {
                                    width: 8
                                    visible: size < 1.0
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        width: Math.min(420, toastTextLabel.implicitWidth + 34)
        height: 52
        radius: 18
        color: Qt.rgba(0.04, 0.05, 0.06, 0.88)
        border.color: Qt.rgba(1, 1, 1, 0.10)
        border.width: 1
        clip: true
        visible: toastVisible
        opacity: toastVisible ? 1 : 0
        z: 90

        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }

        Text {
            id: toastTextLabel
            anchors.centerIn: parent
            text: root.toastText
            color: textPrimary
            font.pixelSize: 13
            font.family: "Inter"
        }
    }

    Item {
        anchors.fill: parent
        visible: hasApp && app.routeBatteryAdvisoryVisible
        z: 120

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        SectionCard {
            width: Math.min(parent.width - 50, 520)
            height: routeBatteryColumn.implicitHeight + 34
            anchors.centerIn: parent
            color: panelBgSoft

            ColumnLayout {
                id: routeBatteryColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    text: "Route battery advisory"
                    color: textPrimary
                    font.pixelSize: 20
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp ? app.routeBatteryAdvisoryText : ""
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Cancel"
                        action: function() { if (hasApp) app.respondRouteBatteryAdvisory("cancel"); }
                    }

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Return home"
                        accentButton: true
                        enabled: hasApp ? app.routeBatteryReturnHomeAvailable : false
                        action: function() { if (hasApp) app.respondRouteBatteryAdvisory("rtl"); }
                    }

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Proceed"
                        warningButton: true
                        action: function() { if (hasApp) app.respondRouteBatteryAdvisory("proceed"); }
                    }
                }
            }
        }
    }

    Item {
        anchors.fill: parent
        visible: hasApp && app.orbitBatteryAdvisoryVisible
        z: 121

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        SectionCard {
            width: Math.min(parent.width - 50, 520)
            height: orbitBatteryColumn.implicitHeight + 34
            anchors.centerIn: parent
            color: panelBgSoft

            ColumnLayout {
                id: orbitBatteryColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    text: "Orbit battery advisory"
                    color: textPrimary
                    font.pixelSize: 20
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp ? app.orbitBatteryAdvisoryText : ""
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Cancel"
                        action: function() { if (hasApp) app.respondOrbitBatteryAdvisory("cancel"); }
                    }

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Return home"
                        accentButton: true
                        enabled: hasApp ? app.orbitBatteryReturnHomeAvailable : false
                        action: function() { if (hasApp) app.respondOrbitBatteryAdvisory("rtl"); }
                    }

                    GlassButton {
                        Layout.fillWidth: true
                        label: "Proceed"
                        warningButton: true
                        action: function() { if (hasApp) app.respondOrbitBatteryAdvisory("proceed"); }
                    }
                }
            }
        }
    }
}
