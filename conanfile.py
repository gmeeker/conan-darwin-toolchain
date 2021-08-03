from conans import ConanFile, tools
from conans.errors import ConanException

import os
import platform
import copy


class DarwinToolchainConan(ConanFile):
    name = "darwin-toolchain"
    version = "1.0.9"
    license = "Apple"
    settings = "os", "arch", "build_type", "os_build", "compiler"
    options = {
        "enable_bitcode": [True, False],
        "enable_arc": [True, False],
        "enable_visibility": [True, False],
        "xcode": [True, False],
    }
    default_options = {
        "enable_bitcode": True,
        "enable_arc": True,
        "enable_visibility": False,
        "xcode": True,
    }
    description = "Darwin toolchain to compile universal macOS/iOS/watchOS/tvOS"
    url = "https://www.github.com/gmeeker/conan-darwin-tooolchain"
    build_policy = "missing"
    exports_sources = "darwin-toolchain.cmake"

    @property
    def cmake_system_name(self):
        if self.settings.os == "Macos":
            return "Darwin"
        return str(self.settings.os)

    @property
    def cmake_system_processor(self):
        return {"x86": "i386",
                "x86_64": "x86_64",
                "armv7": "arm",
                "armv8": "aarch64"}.get(str(self.settings.arch))

    def config_options(self):
        # build_type is only useful for bitcode
        if self.settings.os == "Macos":
            del self.settings.build_type
            del self.options.enable_bitcode

    def configure(self):
        # We export recipes on a Linux machine, thus we have to rely on os_build and not sys.platform
        if self.settings.os_build != "Macos":
            raise Exception("Build machine must be Macos")
        if not tools.is_apple_os(self.settings.os):
            raise Exception("os must be an Apple os")
        if self.settings.os in ["watchOS", "tvOS"] and not self.options.enable_bitcode:
            raise Exception("enable_bitcode is required on watchOS/tvOS")
        if self.settings.os == "watchOS" and self.settings.arch not in ["armv7k", "armv8", "x86", "x86_64"]:
            raise Exception("watchOS: Only supported archs: [armv7k, armv8, x86, x86_64]")

    def package(self):
        self.copy("darwin-toolchain.cmake")

    def package_info_xcode(self):
        self.env_info.CONAN_CMAKE_GENERATOR = "Xcode"
        if not self.settings.os == "Macos" and self.options.enable_bitcode:
            self.env_info.CONAN_CMAKE_XCODE_ATTRIBUTE_EMBED_BITCODE = "YES"
            self.env_info.CMAKE_XCODE_ATTRIBUTE_BITCODE_GENERATION_MODE = "bitcode"
        self.env_info.CONAN_CMAKE_XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC = ("YES" if self.options.enable_arc else "NO")
        self.env_info.CONAN_CMAKE_XCODE_ATTRIBUTE_GCC_SYMBOLS_PRIVATE_EXTERN = ("YES" if not self.options.enable_visibility else "NO")
        self.env_info.CONAN_CMAKE_XCODE_ATTRIBUTE_GCC_INLINES_ARE_PRIVATE_EXTERN = ("YES" if not self.options.enable_visibility else "NO")

        self.env_info.CONAN_CMAKE_OSX_SYSROOT = 'macosx'

    def package_info_makefile(self, darwin_arch, xcrun, sysroot):
        self.cpp_info.sysroot = sysroot

        common_flags = ["-isysroot%s" % sysroot]

        if self.settings.get_safe("os.version"):
            common_flags.append(tools.apple_deployment_target_flag(self.settings.os, self.settings.os.version, os_sdk=self.settings.os.sdk))

        if not self.settings.os == "Macos" and self.options.enable_bitcode:
            if self.settings.build_type == "Debug":
                bitcode_flag = "-fembed-bitcode-marker"
            else:
                bitcode_flag = "-fembed-bitcode"
            common_flags.append(bitcode_flag)
        if self.options.enable_arc:
            common_flags.append("-fobjc-arc")
        else:
            common_flags.append("-no-fobjc-arc")

        # CMake issue, for details look https://github.com/conan-io/conan/issues/2378
        cflags = copy.copy(common_flags)
        for arch in darwin_arch:
            cflags.extend(["-arch", arch])
        cxxflags = copy.copy(cflags)

        if self.options.enable_visibility:
            common_flags.append("-fvisibility=default")
        else:
            cflags.extend(["-fvisibility=hidden"])
            cxxflags.extend(["-fvisibility=hidden", "-fvisibility-inlines-hidden"])

        self.cpp_info.cflags = cflags
        self.cpp_info.cxxflags = cxxflags
        link_flags = copy.copy(common_flags)
        for arch in darwin_arch:
            link_flags.append("-arch %s" % arch)

        self.cpp_info.sharedlinkflags.extend(link_flags)
        self.cpp_info.exelinkflags.extend(link_flags)

        # Set flags in environment too, so that CMake Helper finds them
        cflags_str = " ".join(cflags)
        cxxflags_str = " ".join(cxxflags)
        ldflags_str = " ".join(link_flags)
        self.env_info.CC = xcrun.cc
        self.env_info.CPP = "%s -E" % xcrun.cc
        self.env_info.CXX = xcrun.cxx
        self.env_info.AR = xcrun.ar
        self.env_info.RANLIB = xcrun.ranlib
        self.env_info.STRIP = xcrun.strip

        self.env_info.CFLAGS = cflags_str
        self.env_info.ASFLAGS = cflags_str
        self.env_info.CPPFLAGS = cflags_str
        self.env_info.CXXFLAGS = cxxflags_str
        self.env_info.LDFLAGS = ldflags_str

        self.env_info.CONAN_CMAKE_OSX_SYSROOT = sysroot

    def package_info(self):
        darwin_arch = [self.settings.arch]
        try:
            fat_arch = self.settings.os.fat_arch
            if fat_arch:
                darwin_arch = str(fat_arch).split(';')
        except ConanException:
            pass
        def to_apple_arch(arch):
            if self.settings.os == "watchOS" and arch == "armv8":
                return "arm64_32"
            return tools.to_apple_arch(arch)
        darwin_arch = [to_apple_arch(arch) for arch in darwin_arch]

        xcrun = tools.XCRun(self.settings)
        sysroot = xcrun.sdk_path

        if self.options.xcode:
            self.package_info_xcode()
        else:
            self.package_info_makefile(darwin_arch, xcrun, sysroot)

        self.env_info.CONAN_CMAKE_SYSTEM_NAME = self.cmake_system_name
        if self.settings.get_safe("os.version"):
            self.env_info.CONAN_CMAKE_OSX_DEPLOYMENT_TARGET = str(self.settings.os.version)
        self.env_info.CONAN_CMAKE_OSX_ARCHITECTURES = ";".join(darwin_arch)
        self.env_info.CONAN_CMAKE_SYSTEM_PROCESSOR = self.cmake_system_processor
        self.env_info.CONAN_CMAKE_TOOLCHAIN_FILE = os.path.join(self.package_folder, "darwin-toolchain.cmake")

    def package_id(self):
        self.info.header_only()
