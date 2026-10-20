package com.example.minicrm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the Mini CRM.
 *
 * This application is intentionally tiny. Its only job is to be a realistic
 * "stage" for GitHub Actions security experiments: something that builds,
 * tests and deploys like a real project so the workflows under
 * .github/workflows/ look authentic. The CRM features themselves are not the
 * subject of the security testing — the workflows are.
 */
@SpringBootApplication
public class MiniCrmApplication {

    public static void main(String[] args) {
        SpringApplication.run(MiniCrmApplication.class, args);
    }
}
