#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>

int main(int argc, char **argv)
{
    const char *name = argc > 0 ? argv[0] : "";
    const char *relative = NULL;
    const char *home = getenv("HOME");
    char script[PATH_MAX];

    if (strstr(name, "로버 시작") != NULL)
        relative = "LOONAR/LOONARover/GCS/scripts/start_rover.sh";
    else if (strstr(name, "로버 종료") != NULL)
        relative = "LOONAR/LOONARover/GCS/scripts/stop_rover.sh";
    else if (strstr(name, "실시간 지상국") != NULL)
        relative = "LOONAR/LOONARover/GCS/scripts/start_gcs.sh";
    else if (strstr(name, "영상 수신") != NULL)
        relative = "LOONAR/LOONARover/GCS/scripts/start_video.sh";
    else
    {
        fputs("알 수 없는 LOONAR 실행 파일 이름입니다.\n", stderr);
        return 1;
    }

    if (home == NULL || snprintf(script, sizeof(script), "%s/%s", home, relative) >= (int)sizeof(script))
    {
        fputs("HOME 경로가 없거나 너무 깁니다.\n", stderr);
        return 1;
    }

    execlp("gnome-terminal", "gnome-terminal", "--", script, (char *)NULL);
    perror("gnome-terminal 실행 실패");
    return 1;
}
