/*
 * dualless_vhf.c — Plantilla base de Driver Virtual HID (KMDF + VHF) para Dualless
 *
 * PROPOSITO:
 *   Esqueleto educativo/experimental para Windows Driver Kit (WDK 10/11) usando el
 *   Virtual HID Framework (vhfkm.lib) para exponer un dispositivo virtual HID con
 *   VID 0x054C / PID 0x0CE6 (Sony DualSense USB).
 *
 * IMPORTANTE:
 *   - NO se instala automáticamente ni forma parte del ejecutable de usuario.
 *   - Para cargarlo en Windows x64 se requiere habilitar Test Signing Mode
 *     (incompatible con la mayoría de anti-cheats) o firmarlo con certificado EV +
 *     Microsoft Attestation Signing.
 */

#include <ntddk.h>
#include <wdf.h>
#include <vhf.h>

#define DUALLESS_VID  0x054C
#define DUALLESS_PID  0x0CE6
#define DUALLESS_VER  0x0100

/* IOCTL para enviar informes de entrada (64 bytes, Report ID 0x01) desde user-mode */
#define IOCTL_DUALLESS_SUBMIT_INPUT \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x801, METHOD_BUFFERED, FILE_WRITE_DATA)

typedef struct _DEVICE_CONTEXT {
    VHFHANDLE VhfHandle;
} DEVICE_CONTEXT, *PDEVICE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, DuallessGetDeviceContext)

/*
 * Descriptor HID mínimo de Gamepad compatible como punto de partida.
 * Para emulación completa de DualSense USB (Report ID 0x01 entrada 64B /
 * Report ID 0x02 salida 64B / Feature 0x05 calibración), sustituye este bloque
 * por el descriptor HID completo capturado de un DualSense USB.
 */
static const UCHAR g_DuallessHidDescriptor[] = {
    0x05, 0x01,        /* Usage Page (Generic Desktop) */
    0x09, 0x05,        /* Usage (Game Pad) */
    0xA1, 0x01,        /* Collection (Application) */
    0x85, 0x01,        /*   Report ID (1) */
    0x09, 0x30,        /*   Usage (X) */
    0x09, 0x31,        /*   Usage (Y) */
    0x09, 0x32,        /*   Usage (Z) */
    0x09, 0x35,        /*   Usage (Rz) */
    0x15, 0x00,        /*   Logical Minimum (0) */
    0x26, 0xFF, 0x00,  /*   Logical Maximum (255) */
    0x75, 0x08,        /*   Report Size (8) */
    0x95, 0x3F,        /*   Report Count (63 bytes payload) */
    0x81, 0x02,        /*   Input (Data,Var,Abs) */
    0x85, 0x02,        /*   Report ID (2) */
    0x09, 0x01,        /*   Usage (Vendor Output) */
    0x95, 0x3F,        /*   Report Count (63 bytes payload) */
    0x91, 0x02,        /*   Output (Data,Var,Abs) */
    0xC0               /* End Collection */
};

DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD DuallessEvtDeviceAdd;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL DuallessEvtIoDeviceControl;
EVT_WDF_OBJECT_CONTEXT_CLEANUP DuallessEvtDeviceCleanup;
EVT_VHF_ASYNC_OPERATION DuallessEvtVhfWriteReport;

NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    WDF_DRIVER_CONFIG_INIT(&config, DuallessEvtDeviceAdd);
    return WdfDriverCreate(DriverObject, RegistryPath, WDF_NO_OBJECT_ATTRIBUTES, &config, WDF_NO_HANDLE);
}

VOID
DuallessEvtVhfWriteReport(
    _In_ PVOID VhfClientContext,
    _In_ VHFOPERATIONHANDLE VhfOperationHandle,
    _In_opt_ PVOID VhfOperationContext,
    _In_ PHID_XFER_PACKET HidTransferPacket
)
{
    UNREFERENCED_PARAMETER(VhfClientContext);
    UNREFERENCED_PARAMETER(VhfOperationContext);
    UNREFERENCED_PARAMETER(HidTransferPacket);

    /* Aquí se recibirían los Report ID 0x02 (gatillos adaptativos / hápticos / LED)
       enviados por un juego nativo para reenviarlos al servicio Dualless en user-mode. */
    VhfAsyncOperationComplete(VhfOperationHandle, STATUS_SUCCESS);
}

VOID
DuallessEvtIoDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t OutputBufferLength,
    _In_ size_t InputBufferLength,
    _In_ ULONG IoControlCode
)
{
    UNREFERENCED_PARAMETER(OutputBufferLength);
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;

    if (IoControlCode == IOCTL_DUALLESS_SUBMIT_INPUT && InputBufferLength >= 64) {
        PVOID inBuf = NULL;
        status = WdfRequestRetrieveInputBuffer(Request, 64, &inBuf, NULL);
        if (NT_SUCCESS(status)) {
            WDFDEVICE device = WdfIoQueueGetDevice(Queue);
            PDEVICE_CONTEXT ctx = DuallessGetDeviceContext(device);
            HID_XFER_PACKET packet;
            packet.reportBuffer = (PUCHAR)inBuf;
            packet.reportBufferLen = 64;
            packet.reportId = 0x01;
            status = VhfReadReportSubmit(ctx->VhfHandle, &packet);
        }
    }
    WdfRequestComplete(Request, status);
}

VOID
DuallessEvtDeviceCleanup(
    _In_ WDFOBJECT DeviceObject
)
{
    PDEVICE_CONTEXT ctx = DuallessGetDeviceContext((WDFDEVICE)DeviceObject);
    if (ctx->VhfHandle != WDF_NO_HANDLE) {
        VhfDelete(ctx->VhfHandle, TRUE);
        ctx->VhfHandle = WDF_NO_HANDLE;
    }
}

NTSTATUS
DuallessEvtDeviceAdd(
    _In_ WDFDRIVER Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    UNREFERENCED_PARAMETER(Driver);
    NTSTATUS status;
    WDF_OBJECT_ATTRIBUTES attrs;
    WDFDEVICE device;

    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&attrs, DEVICE_CONTEXT);
    attrs.EvtCleanupCallback = DuallessEvtDeviceCleanup;

    status = WdfDeviceCreate(&DeviceInit, &attrs, &device);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    WDF_IO_QUEUE_CONFIG queueConfig;
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchSequential);
    queueConfig.EvtIoDeviceControl = DuallessEvtIoDeviceControl;
    status = WdfIoQueueCreate(device, &queueConfig, WDF_NO_OBJECT_ATTRIBUTES, WDF_NO_HANDLE);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    PDEVICE_CONTEXT ctx = DuallessGetDeviceContext(device);
    VHF_CONFIG vhfConfig;
    VHF_CONFIG_INIT(
        &vhfConfig,
        WdfDeviceWdmGetDeviceObject(device),
        sizeof(g_DuallessHidDescriptor),
        (PUCHAR)g_DuallessHidDescriptor
    );
    vhfConfig.VendorID = DUALLESS_VID;
    vhfConfig.ProductID = DUALLESS_PID;
    vhfConfig.VersionNumber = DUALLESS_VER;
    vhfConfig.EvtVhfAsyncOperationWriteReport = DuallessEvtVhfWriteReport;

    status = VhfCreate(&vhfConfig, &ctx->VhfHandle);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    return VhfStart(ctx->VhfHandle);
}
